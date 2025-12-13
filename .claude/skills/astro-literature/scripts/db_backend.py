#!/usr/bin/env python3
"""
Database Backend Abstraction Layer

Provides a unified interface for SQLite and PostgreSQL backends.
The backend is selected via the LITDB_BACKEND environment variable:
  - "sqlite" (default): Uses ~/.astro-literature/citations.db
  - "postgresql": Uses PostgreSQL with connection from environment or ~/.pgpass

Environment variables:
  LITDB_BACKEND: "sqlite" or "postgresql" (default: sqlite)
  LITDB_PG_HOST: PostgreSQL host (default: localhost)
  LITDB_PG_PORT: PostgreSQL port (default: 5432)
  LITDB_PG_DATABASE: PostgreSQL database (default: haruspex)
  LITDB_PG_USER: PostgreSQL user (default: roboscientist)
  LITDB_PG_PASSWORD: PostgreSQL password (optional, uses ~/.pgpass if not set)
"""

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# SQLite database location
SQLITE_DB_DIR = Path.home() / '.astro-literature'
SQLITE_DB_PATH = SQLITE_DB_DIR / 'citations.db'


# Schema - compatible with both SQLite and PostgreSQL
# Note: PostgreSQL uses SERIAL instead of AUTOINCREMENT, and different timestamp syntax
SQLITE_SCHEMA = """
-- Papers table: stores paper metadata from ADS
CREATE TABLE IF NOT EXISTS papers (
    bibcode TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,  -- JSON array
    year INTEGER,
    publication TEXT,
    abstract TEXT,
    doi TEXT,
    ads_url TEXT,
    citation_count INTEGER,
    reference_count INTEGER,
    keywords TEXT,  -- JSON array
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Citations table: stores analyzed citation relationships
CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_bibcode TEXT NOT NULL,
    cited_bibcode TEXT NOT NULL,
    classification TEXT CHECK(classification IN
        ('SUPPORTING', 'CONTRASTING', 'REFUTING', 'CONTEXTUAL', 'METHODOLOGICAL', 'NEUTRAL')),
    confidence REAL CHECK(confidence >= 0 AND confidence <= 1),
    context_text TEXT,
    reasoning TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analyzed_by TEXT,
    FOREIGN KEY (citing_bibcode) REFERENCES papers(bibcode),
    FOREIGN KEY (cited_bibcode) REFERENCES papers(bibcode),
    UNIQUE(citing_bibcode, cited_bibcode)
);

-- Hypotheses table: tracks scientific hypotheses/theories and their status
CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('ACTIVE', 'RULED_OUT', 'SUPERSEDED', 'UNCERTAIN'))
        DEFAULT 'UNCERTAIN',
    originating_bibcode TEXT,
    ruling_bibcode TEXT,
    ruled_out_reason TEXT,
    superseded_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (originating_bibcode) REFERENCES papers(bibcode),
    FOREIGN KEY (ruling_bibcode) REFERENCES papers(bibcode)
);

-- Link hypotheses to papers
CREATE TABLE IF NOT EXISTS hypothesis_papers (
    hypothesis_id INTEGER,
    bibcode TEXT,
    stance TEXT CHECK(stance IN ('SUPPORTS', 'REFUTES', 'DISCUSSES', 'PROPOSES')),
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id),
    FOREIGN KEY (bibcode) REFERENCES papers(bibcode),
    PRIMARY KEY (hypothesis_id, bibcode)
);

-- Research sessions table
CREATE TABLE IF NOT EXISTS research_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    summary TEXT,
    consensus_score REAL CHECK(consensus_score >= -1 AND consensus_score <= 1)
);

-- Session papers junction
CREATE TABLE IF NOT EXISTS session_papers (
    session_id INTEGER,
    bibcode TEXT,
    relevance_score REAL,
    is_seed_paper BOOLEAN DEFAULT FALSE,
    depth INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES research_sessions(id),
    FOREIGN KEY (bibcode) REFERENCES papers(bibcode),
    PRIMARY KEY (session_id, bibcode)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_citations_citing ON citations(citing_bibcode);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_bibcode);
CREATE INDEX IF NOT EXISTS idx_citations_classification ON citations(classification);
CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
"""

POSTGRESQL_SCHEMA = """
-- Papers table: stores paper metadata from ADS
CREATE TABLE IF NOT EXISTS papers (
    bibcode TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,  -- JSON array
    year INTEGER,
    publication TEXT,
    abstract TEXT,
    doi TEXT,
    ads_url TEXT,
    citation_count INTEGER,
    reference_count INTEGER,
    keywords TEXT,  -- JSON array
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Citations table: stores analyzed citation relationships
CREATE TABLE IF NOT EXISTS citations (
    id SERIAL PRIMARY KEY,
    citing_bibcode TEXT NOT NULL,
    cited_bibcode TEXT NOT NULL,
    classification TEXT CHECK(classification IN
        ('SUPPORTING', 'CONTRASTING', 'REFUTING', 'CONTEXTUAL', 'METHODOLOGICAL', 'NEUTRAL')),
    confidence REAL CHECK(confidence >= 0 AND confidence <= 1),
    context_text TEXT,
    reasoning TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analyzed_by TEXT,
    FOREIGN KEY (citing_bibcode) REFERENCES papers(bibcode),
    FOREIGN KEY (cited_bibcode) REFERENCES papers(bibcode),
    UNIQUE(citing_bibcode, cited_bibcode)
);

-- Hypotheses table: tracks scientific hypotheses/theories and their status
CREATE TABLE IF NOT EXISTS hypotheses (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('ACTIVE', 'RULED_OUT', 'SUPERSEDED', 'UNCERTAIN'))
        DEFAULT 'UNCERTAIN',
    originating_bibcode TEXT,
    ruling_bibcode TEXT,
    ruled_out_reason TEXT,
    superseded_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (originating_bibcode) REFERENCES papers(bibcode),
    FOREIGN KEY (ruling_bibcode) REFERENCES papers(bibcode)
);

-- Link hypotheses to papers
CREATE TABLE IF NOT EXISTS hypothesis_papers (
    hypothesis_id INTEGER,
    bibcode TEXT,
    stance TEXT CHECK(stance IN ('SUPPORTS', 'REFUTES', 'DISCUSSES', 'PROPOSES')),
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id),
    FOREIGN KEY (bibcode) REFERENCES papers(bibcode),
    PRIMARY KEY (hypothesis_id, bibcode)
);

-- Research sessions table
CREATE TABLE IF NOT EXISTS research_sessions (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    summary TEXT,
    consensus_score REAL CHECK(consensus_score >= -1 AND consensus_score <= 1)
);

-- Session papers junction
CREATE TABLE IF NOT EXISTS session_papers (
    session_id INTEGER,
    bibcode TEXT,
    relevance_score REAL,
    is_seed_paper BOOLEAN DEFAULT FALSE,
    depth INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES research_sessions(id),
    FOREIGN KEY (bibcode) REFERENCES papers(bibcode),
    PRIMARY KEY (session_id, bibcode)
);
"""

POSTGRESQL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_citations_citing ON citations(citing_bibcode);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_bibcode);
CREATE INDEX IF NOT EXISTS idx_citations_classification ON citations(classification);
CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
"""


class DatabaseRow:
    """A dictionary-like object that allows accessing columns by name."""

    def __init__(self, columns: List[str], values: Tuple):
        self._data = dict(zip(columns, values))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    @abstractmethod
    def connect(self) -> None:
        """Establish database connection."""
        pass

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute a query and return cursor."""
        pass

    @abstractmethod
    def executescript(self, script: str) -> None:
        """Execute multiple statements."""
        pass

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    def fetchone(self, cursor: Any) -> Optional[DatabaseRow]:
        """Fetch one row from cursor."""
        pass

    @abstractmethod
    def fetchall(self, cursor: Any) -> List[DatabaseRow]:
        """Fetch all rows from cursor."""
        pass

    @abstractmethod
    def lastrowid(self, cursor: Any) -> int:
        """Get the last inserted row ID."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    def get_placeholder(self) -> str:
        """Get the parameter placeholder style (? for SQLite, %s for PostgreSQL)."""
        pass

    @abstractmethod
    def get_db_path(self) -> str:
        """Get a string describing the database location."""
        pass


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend."""

    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self._columns: Dict[Any, List[str]] = {}

    def connect(self) -> None:
        SQLITE_DB_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(SQLITE_DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.executescript(SQLITE_SCHEMA)

    def execute(self, query: str, params: tuple = ()) -> Any:
        if self.conn is None:
            self.connect()
        cursor = self.conn.execute(query, params)
        # Store column names for this cursor
        if cursor.description:
            self._columns[id(cursor)] = [d[0] for d in cursor.description]
        return cursor

    def executescript(self, script: str) -> None:
        if self.conn is None:
            self.connect()
        self.conn.executescript(script)

    def commit(self) -> None:
        if self.conn:
            self.conn.commit()

    def fetchone(self, cursor: Any) -> Optional[DatabaseRow]:
        row = cursor.fetchone()
        if row is None:
            return None
        # SQLite Row objects can be converted to dict directly
        return dict(row)

    def fetchall(self, cursor: Any) -> List[Dict]:
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def lastrowid(self, cursor: Any) -> int:
        return cursor.lastrowid

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_placeholder(self) -> str:
        return "?"

    def get_db_path(self) -> str:
        return str(SQLITE_DB_PATH)


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL database backend."""

    def __init__(self):
        self.conn = None
        self._columns: Dict[Any, List[str]] = {}
        self._last_id: int = 0

    def _get_connection_params(self) -> Dict[str, str]:
        """Get PostgreSQL connection parameters from environment or pgpass."""
        params = {
            'host': os.environ.get('LITDB_PG_HOST', 'localhost'),
            'port': os.environ.get('LITDB_PG_PORT', '5432'),
            'database': os.environ.get('LITDB_PG_DATABASE', 'haruspex'),
            'user': os.environ.get('LITDB_PG_USER', 'roboscientist'),
        }

        # Password can come from environment or pgpass
        password = os.environ.get('LITDB_PG_PASSWORD')
        if password:
            params['password'] = password
        # Otherwise, psycopg2 will use ~/.pgpass automatically

        return params

    def connect(self) -> None:
        import psycopg2
        params = self._get_connection_params()
        self.conn = psycopg2.connect(**params)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        cursor = self.conn.cursor()
        # Execute schema statements one by one for PostgreSQL
        for statement in POSTGRESQL_SCHEMA.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except Exception:
                    # Table might already exist
                    self.conn.rollback()
                    cursor = self.conn.cursor()

        # Create indexes
        for statement in POSTGRESQL_INDEXES.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except Exception:
                    self.conn.rollback()
                    cursor = self.conn.cursor()

        self.conn.commit()

    def execute(self, query: str, params: tuple = ()) -> Any:
        if self.conn is None:
            self.connect()

        # Convert SQLite-style ? placeholders to PostgreSQL %s
        query = self._convert_placeholders(query)

        cursor = self.conn.cursor()
        cursor.execute(query, params)

        # Store column names
        if cursor.description:
            self._columns[id(cursor)] = [d[0] for d in cursor.description]

        return cursor

    def _convert_placeholders(self, query: str) -> str:
        """Convert ? placeholders to %s for PostgreSQL."""
        # Simple conversion - replace ? with %s
        # Be careful not to replace ? inside strings
        result = []
        in_string = False
        string_char = None
        i = 0
        while i < len(query):
            char = query[i]
            if char in ("'", '"') and (i == 0 or query[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                result.append(char)
            elif char == '?' and not in_string:
                result.append('%s')
            else:
                result.append(char)
            i += 1
        return ''.join(result)

    def executescript(self, script: str) -> None:
        # For PostgreSQL, we need to execute statements one by one
        if self.conn is None:
            self.connect()
        cursor = self.conn.cursor()
        for statement in script.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except Exception:
                    self.conn.rollback()
                    cursor = self.conn.cursor()
        self.conn.commit()

    def commit(self) -> None:
        if self.conn:
            self.conn.commit()

    def fetchone(self, cursor: Any) -> Optional[Dict]:
        row = cursor.fetchone()
        if row is None:
            return None
        columns = self._columns.get(id(cursor), [])
        return dict(zip(columns, row))

    def fetchall(self, cursor: Any) -> List[Dict]:
        rows = cursor.fetchall()
        columns = self._columns.get(id(cursor), [])
        return [dict(zip(columns, row)) for row in rows]

    def lastrowid(self, cursor: Any) -> int:
        # PostgreSQL doesn't have lastrowid - need to use RETURNING
        # This is a limitation; callers should use RETURNING id
        return self._last_id

    def execute_returning(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT with RETURNING id for PostgreSQL."""
        if self.conn is None:
            self.connect()

        query = self._convert_placeholders(query)

        # Add RETURNING id if it's an INSERT
        if query.strip().upper().startswith('INSERT') and 'RETURNING' not in query.upper():
            query = query.rstrip(';') + ' RETURNING id'

        cursor = self.conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        if result:
            self._last_id = result[0]
        return self._last_id

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_placeholder(self) -> str:
        return "%s"

    def get_db_path(self) -> str:
        params = self._get_connection_params()
        return f"postgresql://{params['user']}@{params['host']}:{params['port']}/{params['database']}"


def get_backend() -> DatabaseBackend:
    """Get the appropriate database backend based on environment."""
    backend_type = os.environ.get('LITDB_BACKEND', 'sqlite').lower()

    if backend_type == 'postgresql':
        return PostgreSQLBackend()
    else:
        return SQLiteBackend()


# Convenience functions for common operations
_db: Optional[DatabaseBackend] = None


def get_db() -> DatabaseBackend:
    """Get a shared database connection."""
    global _db
    if _db is None:
        _db = get_backend()
        _db.connect()
    return _db


def json_serialize(obj: Any) -> Optional[str]:
    """Serialize object to JSON, handling None."""
    if obj is None:
        return None
    return json.dumps(obj)


def json_deserialize(s: Optional[str]) -> Any:
    """Deserialize JSON string, handling None."""
    if s is None:
        return None
    return json.loads(s)
