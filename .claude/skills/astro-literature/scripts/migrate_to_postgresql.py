#!/usr/bin/env python3
"""
Migrate SQLite database to PostgreSQL.

Usage:
    python migrate_to_postgresql.py [sqlite_path]

If no path is provided, uses the default ~/.astro-literature/citations.db
"""

import json
import sqlite3
import sys
from pathlib import Path

# Import the PostgreSQL backend
from db_backend import PostgreSQLBackend, json_serialize


def migrate_database(sqlite_path: str):
    """Migrate data from SQLite to PostgreSQL."""

    # Connect to SQLite
    print(f"Connecting to SQLite database: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    # Connect to PostgreSQL
    print("Connecting to PostgreSQL...")
    pg = PostgreSQLBackend()
    pg.connect()
    print(f"Connected to: {pg.get_db_path()}")

    # Drop foreign key constraints for migration
    print("\nDropping foreign key constraints...")
    fk_constraints = [
        ("citations", "citations_citing_bibcode_fkey"),
        ("citations", "citations_cited_bibcode_fkey"),
        ("hypotheses", "hypotheses_originating_bibcode_fkey"),
        ("hypotheses", "hypotheses_ruling_bibcode_fkey"),
        ("hypothesis_papers", "hypothesis_papers_hypothesis_id_fkey"),
        ("hypothesis_papers", "hypothesis_papers_bibcode_fkey"),
        ("session_papers", "session_papers_session_id_fkey"),
        ("session_papers", "session_papers_bibcode_fkey"),
    ]
    for table, constraint in fk_constraints:
        try:
            pg.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
            pg.commit()
        except Exception as e:
            pg.conn.rollback()
            # Constraint might not exist or have different name
            pass

    # Migrate papers
    print("\nMigrating papers...")
    papers = sqlite_conn.execute("SELECT * FROM papers").fetchall()
    migrated_papers = 0
    for paper in papers:
        try:
            pg.execute("""
                INSERT INTO papers
                (bibcode, title, authors, year, publication, abstract, doi, ads_url,
                 citation_count, reference_count, keywords, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bibcode) DO UPDATE SET
                    title = EXCLUDED.title,
                    authors = EXCLUDED.authors,
                    year = EXCLUDED.year,
                    publication = EXCLUDED.publication,
                    abstract = EXCLUDED.abstract,
                    doi = EXCLUDED.doi,
                    ads_url = EXCLUDED.ads_url,
                    citation_count = EXCLUDED.citation_count,
                    reference_count = EXCLUDED.reference_count,
                    keywords = EXCLUDED.keywords,
                    fetched_at = EXCLUDED.fetched_at
            """, (
                paper['bibcode'],
                paper['title'],
                paper['authors'],
                paper['year'],
                paper['publication'],
                paper['abstract'],
                paper['doi'],
                paper['ads_url'],
                paper['citation_count'],
                paper['reference_count'],
                paper['keywords'],
                paper['fetched_at']
            ))
            migrated_papers += 1
        except Exception as e:
            print(f"  Error migrating paper {paper['bibcode']}: {e}")
    pg.commit()
    print(f"  Migrated {migrated_papers} papers")

    # Migrate citations
    print("\nMigrating citations...")
    citations = sqlite_conn.execute("SELECT * FROM citations").fetchall()
    migrated_citations = 0
    for cit in citations:
        try:
            pg.execute("""
                INSERT INTO citations
                (citing_bibcode, cited_bibcode, classification, confidence,
                 context_text, reasoning, analyzed_at, analyzed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (citing_bibcode, cited_bibcode) DO UPDATE SET
                    classification = EXCLUDED.classification,
                    confidence = EXCLUDED.confidence,
                    context_text = EXCLUDED.context_text,
                    reasoning = EXCLUDED.reasoning,
                    analyzed_at = EXCLUDED.analyzed_at,
                    analyzed_by = EXCLUDED.analyzed_by
            """, (
                cit['citing_bibcode'],
                cit['cited_bibcode'],
                cit['classification'],
                cit['confidence'],
                cit['context_text'],
                cit['reasoning'],
                cit['analyzed_at'],
                cit['analyzed_by']
            ))
            pg.commit()
            migrated_citations += 1
        except Exception as e:
            pg.conn.rollback()
            print(f"  Error migrating citation {cit['citing_bibcode']} -> {cit['cited_bibcode']}: {e}")
    print(f"  Migrated {migrated_citations} citations")

    # Migrate hypotheses
    print("\nMigrating hypotheses...")
    hypotheses = sqlite_conn.execute("SELECT * FROM hypotheses").fetchall()
    # Map old IDs to new IDs
    hypothesis_id_map = {}
    migrated_hypotheses = 0
    for hyp in hypotheses:
        try:
            cursor = pg.execute("""
                INSERT INTO hypotheses
                (name, description, status, originating_bibcode, ruling_bibcode,
                 ruled_out_reason, superseded_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                hyp['name'],
                hyp['description'],
                hyp['status'],
                hyp['originating_bibcode'],
                hyp['ruling_bibcode'],
                hyp['ruled_out_reason'],
                hyp['superseded_by'],
                hyp['created_at'],
                hyp['updated_at']
            ))
            row = pg.fetchone(cursor)
            pg.commit()
            if row:
                hypothesis_id_map[hyp['id']] = row['id']
            migrated_hypotheses += 1
        except Exception as e:
            pg.conn.rollback()
            print(f"  Error migrating hypothesis {hyp['name']}: {e}")
    print(f"  Migrated {migrated_hypotheses} hypotheses")

    # Migrate hypothesis_papers
    print("\nMigrating hypothesis_papers...")
    hyp_papers = sqlite_conn.execute("SELECT * FROM hypothesis_papers").fetchall()
    migrated_hyp_papers = 0
    for hp in hyp_papers:
        try:
            new_hyp_id = hypothesis_id_map.get(hp['hypothesis_id'])
            if new_hyp_id:
                pg.execute("""
                    INSERT INTO hypothesis_papers
                    (hypothesis_id, bibcode, stance)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (hypothesis_id, bibcode) DO UPDATE SET
                        stance = EXCLUDED.stance
                """, (
                    new_hyp_id,
                    hp['bibcode'],
                    hp['stance']
                ))
                pg.commit()
                migrated_hyp_papers += 1
        except Exception as e:
            pg.conn.rollback()
            print(f"  Error migrating hypothesis_paper: {e}")
    print(f"  Migrated {migrated_hyp_papers} hypothesis_papers")

    # Migrate research_sessions
    print("\nMigrating research_sessions...")
    sessions = sqlite_conn.execute("SELECT * FROM research_sessions").fetchall()
    session_id_map = {}
    migrated_sessions = 0
    for sess in sessions:
        try:
            cursor = pg.execute("""
                INSERT INTO research_sessions
                (question, started_at, completed_at, summary, consensus_score)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                sess['question'],
                sess['started_at'],
                sess['completed_at'],
                sess['summary'],
                sess['consensus_score']
            ))
            row = pg.fetchone(cursor)
            pg.commit()
            if row:
                session_id_map[sess['id']] = row['id']
            migrated_sessions += 1
        except Exception as e:
            pg.conn.rollback()
            print(f"  Error migrating session: {e}")
    print(f"  Migrated {migrated_sessions} research_sessions")

    # Migrate session_papers
    print("\nMigrating session_papers...")
    sess_papers = sqlite_conn.execute("SELECT * FROM session_papers").fetchall()
    migrated_sess_papers = 0
    for sp in sess_papers:
        try:
            new_sess_id = session_id_map.get(sp['session_id'])
            if new_sess_id:
                pg.execute("""
                    INSERT INTO session_papers
                    (session_id, bibcode, relevance_score, is_seed_paper, depth)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, bibcode) DO UPDATE SET
                        relevance_score = EXCLUDED.relevance_score,
                        is_seed_paper = EXCLUDED.is_seed_paper,
                        depth = EXCLUDED.depth
                """, (
                    new_sess_id,
                    sp['bibcode'],
                    sp['relevance_score'],
                    sp['is_seed_paper'],
                    sp['depth']
                ))
                pg.commit()
                migrated_sess_papers += 1
        except Exception as e:
            pg.conn.rollback()
            print(f"  Error migrating session_paper: {e}")
    print(f"  Migrated {migrated_sess_papers} session_papers")

    # Re-add foreign key constraints
    print("\nRe-adding foreign key constraints...")
    fk_constraints_add = [
        ("citations", "citations_citing_bibcode_fkey", "citing_bibcode", "papers", "bibcode"),
        ("citations", "citations_cited_bibcode_fkey", "cited_bibcode", "papers", "bibcode"),
        ("hypotheses", "hypotheses_originating_bibcode_fkey", "originating_bibcode", "papers", "bibcode"),
        ("hypotheses", "hypotheses_ruling_bibcode_fkey", "ruling_bibcode", "papers", "bibcode"),
        ("hypothesis_papers", "hypothesis_papers_hypothesis_id_fkey", "hypothesis_id", "hypotheses", "id"),
        ("hypothesis_papers", "hypothesis_papers_bibcode_fkey", "bibcode", "papers", "bibcode"),
        ("session_papers", "session_papers_session_id_fkey", "session_id", "research_sessions", "id"),
        ("session_papers", "session_papers_bibcode_fkey", "bibcode", "papers", "bibcode"),
    ]
    for table, constraint, column, ref_table, ref_column in fk_constraints_add:
        try:
            pg.execute(f"""
                ALTER TABLE {table}
                ADD CONSTRAINT {constraint}
                FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column})
            """)
            pg.commit()
        except Exception as e:
            pg.conn.rollback()
            # Constraint might already exist
            pass

    # Close connections
    sqlite_conn.close()
    pg.close()

    print("\n" + "=" * 50)
    print("Migration complete!")
    print("=" * 50)
    print(f"Papers:           {migrated_papers}")
    print(f"Citations:        {migrated_citations}")
    print(f"Hypotheses:       {migrated_hypotheses}")
    print(f"Hypothesis links: {migrated_hyp_papers}")
    print(f"Sessions:         {migrated_sessions}")
    print(f"Session papers:   {migrated_sess_papers}")


def main():
    if len(sys.argv) > 1:
        sqlite_path = sys.argv[1]
    else:
        sqlite_path = str(Path.home() / '.astro-literature' / 'citations.db')

    if not Path(sqlite_path).exists():
        print(f"Error: SQLite database not found: {sqlite_path}")
        sys.exit(1)

    migrate_database(sqlite_path)


if __name__ == '__main__':
    main()
