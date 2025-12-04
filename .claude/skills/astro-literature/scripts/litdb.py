#!/usr/bin/env python3
"""
Literature Database CLI Tool

Manages the SQLite database for storing papers, citations, and research sessions.
Database location: ~/.astro-literature/citations.db
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Database location
DB_DIR = Path.home() / '.astro-literature'
DB_PATH = DB_DIR / 'citations.db'

SCHEMA = """
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
        ('SUPPORTING', 'CONTRASTING', 'CONTEXTUAL', 'METHODOLOGICAL', 'NEUTRAL')),
    confidence REAL CHECK(confidence >= 0 AND confidence <= 1),
    context_text TEXT,
    reasoning TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    analyzed_by TEXT,  -- agent identifier
    FOREIGN KEY (citing_bibcode) REFERENCES papers(bibcode),
    FOREIGN KEY (cited_bibcode) REFERENCES papers(bibcode),
    UNIQUE(citing_bibcode, cited_bibcode)
);

-- Research sessions table: tracks research queries
CREATE TABLE IF NOT EXISTS research_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    summary TEXT,
    consensus_score REAL CHECK(consensus_score >= -1 AND consensus_score <= 1)
);

-- Session papers junction: links sessions to analyzed papers
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

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_citations_citing ON citations(citing_bibcode);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_bibcode);
CREATE INDEX IF NOT EXISTS idx_citations_classification ON citations(classification);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
"""


def get_db() -> sqlite3.Connection:
    """Get database connection, creating database if needed."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def json_serialize(obj):
    """Serialize object to JSON, handling None."""
    if obj is None:
        return None
    return json.dumps(obj)


def json_deserialize(s):
    """Deserialize JSON string, handling None."""
    if s is None:
        return None
    return json.loads(s)


# ============================================================================
# Paper Commands
# ============================================================================

def papers_add(args):
    """Add a paper to the database."""
    conn = get_db()

    if args.json:
        data = json.loads(args.json)
        bibcode = data.get('bibcode', args.bibcode)
    else:
        data = {}
        bibcode = args.bibcode

    if not bibcode:
        print("Error: bibcode is required", file=sys.stderr)
        return 1

    conn.execute("""
        INSERT OR REPLACE INTO papers
        (bibcode, title, authors, year, publication, abstract, doi, ads_url,
         citation_count, reference_count, keywords, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        bibcode,
        data.get('title', args.title),
        json_serialize(data.get('authors')),
        data.get('year'),
        data.get('publication'),
        data.get('abstract'),
        data.get('doi'),
        data.get('ads_url', f"https://ui.adsabs.harvard.edu/abs/{bibcode}"),
        data.get('citation_count'),
        data.get('reference_count'),
        json_serialize(data.get('keywords')),
        datetime.now().isoformat()
    ))
    conn.commit()
    print(f"Added paper: {bibcode}")
    return 0


def papers_get(args):
    """Get a paper by bibcode."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM papers WHERE bibcode = ?", (args.bibcode,)
    ).fetchone()

    if not row:
        print(f"Paper not found: {args.bibcode}", file=sys.stderr)
        return 1

    paper = dict(row)
    paper['authors'] = json_deserialize(paper['authors'])
    paper['keywords'] = json_deserialize(paper['keywords'])

    if args.format == 'json':
        print(json.dumps(paper, indent=2))
    else:
        print(f"Bibcode: {paper['bibcode']}")
        print(f"Title: {paper['title']}")
        print(f"Authors: {', '.join(paper['authors'][:3]) if paper['authors'] else 'N/A'}...")
        print(f"Year: {paper['year']}")
        print(f"Publication: {paper['publication']}")
        print(f"Citations: {paper['citation_count']}")
        print(f"URL: {paper['ads_url']}")
    return 0


def papers_list(args):
    """List papers in the database."""
    conn = get_db()

    query = "SELECT bibcode, title, year, citation_count FROM papers"
    params = []

    if args.year:
        query += " WHERE year = ?"
        params.append(args.year)

    query += " ORDER BY citation_count DESC"

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(query, params).fetchall()

    if args.format == 'json':
        print(json.dumps([dict(r) for r in rows], indent=2))
    else:
        for row in rows:
            title = row['title'][:50] + '...' if row['title'] and len(row['title']) > 50 else row['title']
            print(f"{row['bibcode']} ({row['year']}) [{row['citation_count']} cites] {title}")
    return 0


def papers_count(args):
    """Count papers in the database."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(count)
    return 0


# ============================================================================
# Citation Commands
# ============================================================================

def citations_add(args):
    """Add a citation relationship."""
    conn = get_db()

    try:
        conn.execute("""
            INSERT OR REPLACE INTO citations
            (citing_bibcode, cited_bibcode, classification, confidence,
             context_text, reasoning, analyzed_at, analyzed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            args.citing,
            args.cited,
            args.classification.upper(),
            args.confidence,
            args.context,
            args.reasoning,
            datetime.now().isoformat(),
            args.agent or 'manual'
        ))
        conn.commit()
        print(f"Added citation: {args.citing} -> {args.cited} ({args.classification})")
        return 0
    except sqlite3.IntegrityError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def citations_list(args):
    """List citations."""
    conn = get_db()

    query = "SELECT * FROM citations WHERE 1=1"
    params = []

    if args.bibcode:
        query += " AND (citing_bibcode = ? OR cited_bibcode = ?)"
        params.extend([args.bibcode, args.bibcode])

    if args.citing:
        query += " AND citing_bibcode = ?"
        params.append(args.citing)

    if args.cited:
        query += " AND cited_bibcode = ?"
        params.append(args.cited)

    if args.classification:
        query += " AND classification = ?"
        params.append(args.classification.upper())

    query += " ORDER BY analyzed_at DESC"

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(query, params).fetchall()

    if args.format == 'json':
        print(json.dumps([dict(r) for r in rows], indent=2))
    else:
        for row in rows:
            conf = f"[{row['confidence']:.2f}]" if row['confidence'] else "[N/A]"
            print(f"{row['citing_bibcode']} -> {row['cited_bibcode']}: "
                  f"{row['classification']} {conf}")
            if args.verbose and row['reasoning']:
                print(f"  Reasoning: {row['reasoning'][:80]}...")
    return 0


def citations_summary(args):
    """Show citation classification summary."""
    conn = get_db()

    if args.bibcode:
        # Summary for a specific paper (as cited)
        rows = conn.execute("""
            SELECT classification, COUNT(*) as count,
                   AVG(confidence) as avg_confidence
            FROM citations
            WHERE cited_bibcode = ?
            GROUP BY classification
        """, (args.bibcode,)).fetchall()

        print(f"Citation summary for: {args.bibcode}")
        print("-" * 40)
    else:
        # Overall summary
        rows = conn.execute("""
            SELECT classification, COUNT(*) as count,
                   AVG(confidence) as avg_confidence
            FROM citations
            GROUP BY classification
        """).fetchall()

        print("Overall citation summary")
        print("-" * 40)

    total = sum(r['count'] for r in rows)
    for row in rows:
        pct = (row['count'] / total * 100) if total > 0 else 0
        conf = f"(avg conf: {row['avg_confidence']:.2f})" if row['avg_confidence'] else ""
        print(f"  {row['classification']:15} {row['count']:5} ({pct:5.1f}%) {conf}")

    print("-" * 40)
    print(f"  Total: {total}")

    # Calculate consensus score
    supporting = next((r['count'] for r in rows if r['classification'] == 'SUPPORTING'), 0)
    contrasting = next((r['count'] for r in rows if r['classification'] == 'CONTRASTING'), 0)

    if supporting + contrasting > 0:
        consensus = (supporting - contrasting) / (supporting + contrasting)
        print(f"  Consensus score: {consensus:+.2f}")
    return 0


def citations_count(args):
    """Count citations in the database."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    print(count)
    return 0


# ============================================================================
# Session Commands
# ============================================================================

def session_create(args):
    """Create a new research session."""
    conn = get_db()

    cursor = conn.execute("""
        INSERT INTO research_sessions (question, started_at)
        VALUES (?, ?)
    """, (args.question, datetime.now().isoformat()))
    conn.commit()

    session_id = cursor.lastrowid
    print(f"Created session {session_id}: {args.question}")
    return 0


def session_list(args):
    """List research sessions."""
    conn = get_db()

    rows = conn.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM session_papers WHERE session_id = s.id) as paper_count
        FROM research_sessions s
        ORDER BY started_at DESC
        LIMIT ?
    """, (args.limit or 20,)).fetchall()

    if args.format == 'json':
        print(json.dumps([dict(r) for r in rows], indent=2))
    else:
        for row in rows:
            status = "completed" if row['completed_at'] else "in progress"
            print(f"[{row['id']}] {status} ({row['paper_count']} papers)")
            print(f"    Q: {row['question'][:60]}...")
            if row['consensus_score'] is not None:
                print(f"    Consensus: {row['consensus_score']:+.2f}")
    return 0


def session_complete(args):
    """Mark a session as complete."""
    conn = get_db()

    conn.execute("""
        UPDATE research_sessions
        SET completed_at = ?, summary = ?, consensus_score = ?
        WHERE id = ?
    """, (
        datetime.now().isoformat(),
        args.summary,
        args.consensus_score,
        args.id
    ))
    conn.commit()
    print(f"Completed session {args.id}")
    return 0


def session_add_paper(args):
    """Add a paper to a session."""
    conn = get_db()

    conn.execute("""
        INSERT OR REPLACE INTO session_papers
        (session_id, bibcode, relevance_score, is_seed_paper, depth)
        VALUES (?, ?, ?, ?, ?)
    """, (
        args.session_id,
        args.bibcode,
        args.relevance,
        args.seed,
        args.depth or 0
    ))
    conn.commit()
    print(f"Added {args.bibcode} to session {args.session_id}")
    return 0


# ============================================================================
# Export/Stats Commands
# ============================================================================

def export_data(args):
    """Export database data."""
    conn = get_db()

    data = {
        'exported_at': datetime.now().isoformat(),
        'papers': [],
        'citations': [],
    }

    if args.session_id:
        # Export specific session
        session = conn.execute(
            "SELECT * FROM research_sessions WHERE id = ?",
            (args.session_id,)
        ).fetchone()

        if not session:
            print(f"Session {args.session_id} not found", file=sys.stderr)
            return 1

        data['session'] = dict(session)

        # Get session papers
        bibcodes = conn.execute(
            "SELECT bibcode FROM session_papers WHERE session_id = ?",
            (args.session_id,)
        ).fetchall()
        bibcode_list = [r['bibcode'] for r in bibcodes]

        if bibcode_list:
            placeholders = ','.join('?' * len(bibcode_list))
            papers = conn.execute(
                f"SELECT * FROM papers WHERE bibcode IN ({placeholders})",
                bibcode_list
            ).fetchall()
            data['papers'] = [dict(r) for r in papers]

            citations = conn.execute(f"""
                SELECT * FROM citations
                WHERE citing_bibcode IN ({placeholders})
                   OR cited_bibcode IN ({placeholders})
            """, bibcode_list + bibcode_list).fetchall()
            data['citations'] = [dict(r) for r in citations]
    else:
        # Export all
        papers = conn.execute("SELECT * FROM papers").fetchall()
        data['papers'] = [dict(r) for r in papers]

        citations = conn.execute("SELECT * FROM citations").fetchall()
        data['citations'] = [dict(r) for r in citations]

    if args.format == 'json':
        output = json.dumps(data, indent=2)
    else:
        # CSV format - just citations
        lines = ['citing_bibcode,cited_bibcode,classification,confidence']
        for c in data['citations']:
            lines.append(f"{c['citing_bibcode']},{c['cited_bibcode']},"
                        f"{c['classification']},{c.get('confidence', '')}")
        output = '\n'.join(lines)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Exported to {args.output}", file=sys.stderr)
    else:
        print(output)
    return 0


def show_stats(args):
    """Show database statistics."""
    conn = get_db()

    paper_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    citation_count = conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    session_count = conn.execute("SELECT COUNT(*) FROM research_sessions").fetchone()[0]

    print("=" * 50)
    print("LITERATURE DATABASE STATISTICS")
    print("=" * 50)
    print(f"Database: {DB_PATH}")
    print(f"Papers: {paper_count}")
    print(f"Citations: {citation_count}")
    print(f"Sessions: {session_count}")

    if citation_count > 0:
        print("\nCitation breakdown:")
        rows = conn.execute("""
            SELECT classification, COUNT(*) as count
            FROM citations
            GROUP BY classification
            ORDER BY count DESC
        """).fetchall()
        for row in rows:
            print(f"  {row['classification']:15} {row['count']}")

    if paper_count > 0:
        print("\nTop cited papers in database:")
        rows = conn.execute("""
            SELECT bibcode, title, citation_count
            FROM papers
            ORDER BY citation_count DESC
            LIMIT 5
        """).fetchall()
        for row in rows:
            title = row['title'][:40] + '...' if row['title'] and len(row['title']) > 40 else row['title']
            print(f"  [{row['citation_count']:4}] {title}")

    return 0


def reset_db(args):
    """Reset (delete) the database."""
    if not args.confirm:
        print("Use --confirm to actually delete the database", file=sys.stderr)
        return 1

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Deleted database: {DB_PATH}")
    else:
        print("Database does not exist")
    return 0


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Literature Database CLI - manages papers and citations',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Papers commands
    papers_parser = subparsers.add_parser('papers', help='Paper commands')
    papers_sub = papers_parser.add_subparsers(dest='subcommand')

    p_add = papers_sub.add_parser('add', help='Add a paper')
    p_add.add_argument('--bibcode', '-b', help='ADS bibcode')
    p_add.add_argument('--title', '-t', help='Paper title')
    p_add.add_argument('--json', '-j', help='JSON data for paper')
    p_add.set_defaults(func=papers_add)

    p_get = papers_sub.add_parser('get', help='Get paper details')
    p_get.add_argument('--bibcode', '-b', required=True, help='ADS bibcode')
    p_get.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    p_get.set_defaults(func=papers_get)

    p_list = papers_sub.add_parser('list', help='List papers')
    p_list.add_argument('--year', '-y', type=int, help='Filter by year')
    p_list.add_argument('--limit', '-n', type=int, default=20, help='Limit results')
    p_list.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    p_list.set_defaults(func=papers_list)

    p_count = papers_sub.add_parser('count', help='Count papers')
    p_count.set_defaults(func=papers_count)

    # Citations commands
    cit_parser = subparsers.add_parser('citations', help='Citation commands')
    cit_sub = cit_parser.add_subparsers(dest='subcommand')

    c_add = cit_sub.add_parser('add', help='Add a citation')
    c_add.add_argument('--citing', required=True, help='Citing paper bibcode')
    c_add.add_argument('--cited', required=True, help='Cited paper bibcode')
    c_add.add_argument('--classification', '-c', required=True,
                       choices=['SUPPORTING', 'CONTRASTING', 'CONTEXTUAL',
                               'METHODOLOGICAL', 'NEUTRAL'],
                       help='Citation classification')
    c_add.add_argument('--confidence', type=float, help='Confidence score 0-1')
    c_add.add_argument('--context', help='Citation context text')
    c_add.add_argument('--reasoning', help='Classification reasoning')
    c_add.add_argument('--agent', help='Agent identifier')
    c_add.set_defaults(func=citations_add)

    c_list = cit_sub.add_parser('list', help='List citations')
    c_list.add_argument('--bibcode', '-b', help='Filter by paper (citing or cited)')
    c_list.add_argument('--citing', help='Filter by citing paper')
    c_list.add_argument('--cited', help='Filter by cited paper')
    c_list.add_argument('--classification', '-c', help='Filter by classification')
    c_list.add_argument('--limit', '-n', type=int, default=50, help='Limit results')
    c_list.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    c_list.add_argument('--verbose', '-v', action='store_true', help='Show reasoning')
    c_list.set_defaults(func=citations_list)

    c_summary = cit_sub.add_parser('summary', help='Citation summary')
    c_summary.add_argument('--bibcode', '-b', help='Summary for specific paper')
    c_summary.set_defaults(func=citations_summary)

    c_count = cit_sub.add_parser('count', help='Count citations')
    c_count.set_defaults(func=citations_count)

    # Session commands
    sess_parser = subparsers.add_parser('session', help='Session commands')
    sess_sub = sess_parser.add_subparsers(dest='subcommand')

    s_create = sess_sub.add_parser('create', help='Create session')
    s_create.add_argument('--question', '-q', required=True, help='Research question')
    s_create.set_defaults(func=session_create)

    s_list = sess_sub.add_parser('list', help='List sessions')
    s_list.add_argument('--limit', '-n', type=int, default=20, help='Limit results')
    s_list.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    s_list.set_defaults(func=session_list)

    s_complete = sess_sub.add_parser('complete', help='Complete session')
    s_complete.add_argument('--id', type=int, required=True, help='Session ID')
    s_complete.add_argument('--summary', '-s', help='Session summary')
    s_complete.add_argument('--consensus-score', type=float, help='Consensus score -1 to 1')
    s_complete.set_defaults(func=session_complete)

    s_add_paper = sess_sub.add_parser('add-paper', help='Add paper to session')
    s_add_paper.add_argument('--session-id', type=int, required=True, help='Session ID')
    s_add_paper.add_argument('--bibcode', '-b', required=True, help='Paper bibcode')
    s_add_paper.add_argument('--relevance', type=float, help='Relevance score')
    s_add_paper.add_argument('--seed', action='store_true', help='Mark as seed paper')
    s_add_paper.add_argument('--depth', type=int, help='Analysis depth level')
    s_add_paper.set_defaults(func=session_add_paper)

    # Export command
    exp_parser = subparsers.add_parser('export', help='Export data')
    exp_parser.add_argument('--session-id', type=int, help='Export specific session')
    exp_parser.add_argument('--format', '-f', choices=['json', 'csv'], default='json')
    exp_parser.add_argument('--output', '-o', help='Output file')
    exp_parser.set_defaults(func=export_data)

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.set_defaults(func=show_stats)

    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Reset database')
    reset_parser.add_argument('--confirm', action='store_true', help='Confirm deletion')
    reset_parser.set_defaults(func=reset_db)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, 'func'):
        return args.func(args)
    else:
        # Subcommand not specified
        if args.command == 'papers':
            papers_parser.print_help()
        elif args.command == 'citations':
            cit_parser.print_help()
        elif args.command == 'session':
            sess_parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
