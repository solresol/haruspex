#!/usr/bin/env python3
"""
Literature Database CLI Tool

Manages the database for storing papers, citations, and research sessions.
Supports both SQLite (default) and PostgreSQL backends.

Database backends:
  SQLite (default): ~/.astro-literature/citations.db
  PostgreSQL: Set LITDB_BACKEND=postgresql

Environment variables:
  LITDB_BACKEND: "sqlite" (default) or "postgresql"
  LITDB_PG_HOST: PostgreSQL host (default: localhost)
  LITDB_PG_PORT: PostgreSQL port (default: 5432)
  LITDB_PG_DATABASE: PostgreSQL database (default: haruspex)
  LITDB_PG_USER: PostgreSQL user (default: roboscientist)
  LITDB_PG_PASSWORD: PostgreSQL password (optional, uses ~/.pgpass if not set)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import the database backend abstraction
from db_backend import get_db, json_serialize, json_deserialize, DatabaseBackend


# ============================================================================
# Paper Commands
# ============================================================================

def papers_add(args):
    """Add a paper to the database."""
    db = get_db()

    if args.json:
        data = json.loads(args.json)
        bibcode = data.get('bibcode', args.bibcode)
    else:
        data = {}
        bibcode = args.bibcode

    if not bibcode:
        print("Error: bibcode is required", file=sys.stderr)
        return 1

    # Use INSERT ... ON CONFLICT for PostgreSQL compatibility
    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
    if backend == 'postgresql':
        query = """
            INSERT INTO papers
            (bibcode, title, authors, year, publication, abstract, doi, ads_url,
             citation_count, reference_count, keywords, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        """
    else:
        query = """
            INSERT OR REPLACE INTO papers
            (bibcode, title, authors, year, publication, abstract, doi, ads_url,
             citation_count, reference_count, keywords, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    db.execute(query, (
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
    db.commit()
    print(f"Added paper: {bibcode}")
    return 0


def papers_get(args):
    """Get a paper by bibcode."""
    db = get_db()
    cursor = db.execute(
        "SELECT * FROM papers WHERE bibcode = ?", (args.bibcode,)
    )
    row = db.fetchone(cursor)

    if not row:
        print(f"Paper not found: {args.bibcode}", file=sys.stderr)
        return 1

    paper = dict(row)
    paper['authors'] = json_deserialize(paper['authors'])
    paper['keywords'] = json_deserialize(paper['keywords'])

    if args.format == 'json':
        print(json.dumps(paper, indent=2, default=str))
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
    db = get_db()

    query = "SELECT bibcode, title, year, citation_count FROM papers"
    params = []

    if args.year:
        query += " WHERE year = ?"
        params.append(args.year)

    query += " ORDER BY citation_count DESC"

    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    cursor = db.execute(query, tuple(params))
    rows = db.fetchall(cursor)

    if args.format == 'json':
        print(json.dumps(rows, indent=2, default=str))
    else:
        for row in rows:
            title = row['title'][:50] + '...' if row['title'] and len(row['title']) > 50 else row['title']
            print(f"{row['bibcode']} ({row['year']}) [{row['citation_count']} cites] {title}")
    return 0


def papers_count(args):
    """Count papers in the database."""
    db = get_db()
    cursor = db.execute("SELECT COUNT(*) as cnt FROM papers")
    row = db.fetchone(cursor)
    print(row['cnt'])
    return 0


# ============================================================================
# Citation Commands
# ============================================================================

def citations_add(args):
    """Add a citation relationship."""
    db = get_db()

    try:
        # Use INSERT ... ON CONFLICT for PostgreSQL compatibility
        backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
        if backend == 'postgresql':
            query = """
                INSERT INTO citations
                (citing_bibcode, cited_bibcode, classification, confidence,
                 context_text, reasoning, analyzed_at, analyzed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (citing_bibcode, cited_bibcode) DO UPDATE SET
                    classification = EXCLUDED.classification,
                    confidence = EXCLUDED.confidence,
                    context_text = EXCLUDED.context_text,
                    reasoning = EXCLUDED.reasoning,
                    analyzed_at = EXCLUDED.analyzed_at,
                    analyzed_by = EXCLUDED.analyzed_by
            """
        else:
            query = """
                INSERT OR REPLACE INTO citations
                (citing_bibcode, cited_bibcode, classification, confidence,
                 context_text, reasoning, analyzed_at, analyzed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

        db.execute(query, (
            args.citing,
            args.cited,
            args.classification.upper(),
            args.confidence,
            args.context,
            args.reasoning,
            datetime.now().isoformat(),
            args.agent or 'manual'
        ))
        db.commit()
        print(f"Added citation: {args.citing} -> {args.cited} ({args.classification})")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def citations_list(args):
    """List citations."""
    db = get_db()

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

    cursor = db.execute(query, tuple(params))
    rows = db.fetchall(cursor)

    if args.format == 'json':
        print(json.dumps(rows, indent=2, default=str))
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
    db = get_db()

    if args.bibcode:
        # Summary for a specific paper (as cited)
        cursor = db.execute("""
            SELECT classification, COUNT(*) as count,
                   AVG(confidence) as avg_confidence
            FROM citations
            WHERE cited_bibcode = ?
            GROUP BY classification
        """, (args.bibcode,))
        rows = db.fetchall(cursor)

        print(f"Citation summary for: {args.bibcode}")
        print("-" * 40)
    else:
        # Overall summary
        cursor = db.execute("""
            SELECT classification, COUNT(*) as count,
                   AVG(confidence) as avg_confidence
            FROM citations
            GROUP BY classification
        """)
        rows = db.fetchall(cursor)

        print("Overall citation summary")
        print("-" * 40)

    total = sum(r['count'] for r in rows)
    for row in rows:
        pct = (row['count'] / total * 100) if total > 0 else 0
        conf = f"(avg conf: {row['avg_confidence']:.2f})" if row['avg_confidence'] else ""
        print(f"  {row['classification']:15} {row['count']:5} ({pct:5.1f}%) {conf}")

    print("-" * 40)
    print(f"  Total: {total}")

    # Calculate consensus score (REFUTING counts double against)
    supporting = next((r['count'] for r in rows if r['classification'] == 'SUPPORTING'), 0)
    contrasting = next((r['count'] for r in rows if r['classification'] == 'CONTRASTING'), 0)
    refuting = next((r['count'] for r in rows if r['classification'] == 'REFUTING'), 0)

    against = contrasting + (refuting * 2)  # Refuting counts double
    if supporting + against > 0:
        consensus = (supporting - against) / (supporting + against)
        print(f"  Consensus score: {consensus:+.2f}")

    if refuting > 0:
        print(f"  {refuting} REFUTING citations - hypothesis may be ruled out")
    return 0


def citations_count(args):
    """Count citations in the database."""
    db = get_db()
    cursor = db.execute("SELECT COUNT(*) as cnt FROM citations")
    row = db.fetchone(cursor)
    print(row['cnt'])
    return 0


# ============================================================================
# Session Commands
# ============================================================================

def session_create(args):
    """Create a new research session."""
    db = get_db()

    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
    if backend == 'postgresql':
        # PostgreSQL uses RETURNING to get the new ID
        cursor = db.execute("""
            INSERT INTO research_sessions (question, started_at)
            VALUES (?, ?)
            RETURNING id
        """, (args.question, datetime.now().isoformat()))
        row = db.fetchone(cursor)
        session_id = row['id'] if row else 0
    else:
        cursor = db.execute("""
            INSERT INTO research_sessions (question, started_at)
            VALUES (?, ?)
        """, (args.question, datetime.now().isoformat()))
        session_id = db.lastrowid(cursor)

    db.commit()
    print(f"Created session {session_id}: {args.question}")
    return 0


def session_list(args):
    """List research sessions."""
    db = get_db()

    cursor = db.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM session_papers WHERE session_id = s.id) as paper_count
        FROM research_sessions s
        ORDER BY started_at DESC
        LIMIT ?
    """, (args.limit or 20,))
    rows = db.fetchall(cursor)

    if args.format == 'json':
        print(json.dumps(rows, indent=2, default=str))
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
    db = get_db()

    db.execute("""
        UPDATE research_sessions
        SET completed_at = ?, summary = ?, consensus_score = ?
        WHERE id = ?
    """, (
        datetime.now().isoformat(),
        args.summary,
        args.consensus_score,
        args.id
    ))
    db.commit()
    print(f"Completed session {args.id}")
    return 0


def session_add_paper(args):
    """Add a paper to a session."""
    db = get_db()

    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
    if backend == 'postgresql':
        query = """
            INSERT INTO session_papers
            (session_id, bibcode, relevance_score, is_seed_paper, depth)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (session_id, bibcode) DO UPDATE SET
                relevance_score = EXCLUDED.relevance_score,
                is_seed_paper = EXCLUDED.is_seed_paper,
                depth = EXCLUDED.depth
        """
    else:
        query = """
            INSERT OR REPLACE INTO session_papers
            (session_id, bibcode, relevance_score, is_seed_paper, depth)
            VALUES (?, ?, ?, ?, ?)
        """

    db.execute(query, (
        args.session_id,
        args.bibcode,
        args.relevance,
        args.seed,
        args.depth or 0
    ))
    db.commit()
    print(f"Added {args.bibcode} to session {args.session_id}")
    return 0


# ============================================================================
# Hypothesis Commands
# ============================================================================

def hypothesis_add(args):
    """Add a hypothesis to track."""
    db = get_db()

    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
    if backend == 'postgresql':
        cursor = db.execute("""
            INSERT INTO hypotheses
            (name, description, status, originating_bibcode, ruling_bibcode,
             ruled_out_reason, superseded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, (
            args.name,
            args.description,
            args.status,
            args.origin,
            args.ruling,
            args.reason,
            args.superseded_by
        ))
        row = db.fetchone(cursor)
        hypothesis_id = row['id'] if row else 0
    else:
        cursor = db.execute("""
            INSERT INTO hypotheses
            (name, description, status, originating_bibcode, ruling_bibcode,
             ruled_out_reason, superseded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            args.name,
            args.description,
            args.status,
            args.origin,
            args.ruling,
            args.reason,
            args.superseded_by
        ))
        hypothesis_id = db.lastrowid(cursor)

    db.commit()
    print(f"Added hypothesis [{hypothesis_id}]: {args.name} ({args.status})")
    return 0


def hypothesis_list(args):
    """List hypotheses."""
    db = get_db()

    query = "SELECT * FROM hypotheses"
    params = []

    if args.status:
        query += " WHERE status = ?"
        params.append(args.status.upper())

    query += " ORDER BY updated_at DESC"

    cursor = db.execute(query, tuple(params))
    rows = db.fetchall(cursor)

    if args.format == 'json':
        print(json.dumps(rows, indent=2, default=str))
    else:
        if not rows:
            print("No hypotheses tracked yet.")
            return 0

        for row in rows:
            status_icon = {
                'ACTIVE': '✓',
                'RULED_OUT': '✗',
                'SUPERSEDED': '→',
                'UNCERTAIN': '?'
            }.get(row['status'], '?')

            print(f"[{row['id']}] {status_icon} {row['name']} ({row['status']})")
            if row['description']:
                print(f"    {row['description'][:60]}...")
            if row['status'] == 'RULED_OUT' and row['ruled_out_reason']:
                print(f"    Ruled out: {row['ruled_out_reason'][:60]}...")
            if row['status'] == 'SUPERSEDED' and row['superseded_by']:
                print(f"    Superseded by: {row['superseded_by']}")
    return 0


def hypothesis_update(args):
    """Update a hypothesis."""
    db = get_db()

    updates = ["updated_at = ?"]
    params = [datetime.now().isoformat()]

    if args.status:
        updates.append("status = ?")
        params.append(args.status)
    if args.ruling:
        updates.append("ruling_bibcode = ?")
        params.append(args.ruling)
    if args.reason:
        updates.append("ruled_out_reason = ?")
        params.append(args.reason)
    if args.superseded_by:
        updates.append("superseded_by = ?")
        params.append(args.superseded_by)

    params.append(args.id)

    db.execute(f"""
        UPDATE hypotheses
        SET {', '.join(updates)}
        WHERE id = ?
    """, tuple(params))
    db.commit()
    print(f"Updated hypothesis {args.id}")
    return 0


def hypothesis_link(args):
    """Link a paper to a hypothesis."""
    db = get_db()

    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
    if backend == 'postgresql':
        query = """
            INSERT INTO hypothesis_papers
            (hypothesis_id, bibcode, stance)
            VALUES (?, ?, ?)
            ON CONFLICT (hypothesis_id, bibcode) DO UPDATE SET
                stance = EXCLUDED.stance
        """
    else:
        query = """
            INSERT OR REPLACE INTO hypothesis_papers
            (hypothesis_id, bibcode, stance)
            VALUES (?, ?, ?)
        """

    db.execute(query, (args.hypothesis_id, args.bibcode, args.stance))
    db.commit()
    print(f"Linked {args.bibcode} to hypothesis {args.hypothesis_id} ({args.stance})")
    return 0


def hypothesis_ruled_out(args):
    """List ruled-out hypotheses with details."""
    db = get_db()

    cursor = db.execute("""
        SELECT h.*, p.title as ruling_paper_title
        FROM hypotheses h
        LEFT JOIN papers p ON h.ruling_bibcode = p.bibcode
        WHERE h.status IN ('RULED_OUT', 'SUPERSEDED')
        ORDER BY h.updated_at DESC
    """)
    rows = db.fetchall(cursor)

    if args.format == 'json':
        print(json.dumps(rows, indent=2, default=str))
    else:
        if not rows:
            print("No ruled-out hypotheses yet.")
            return 0

        print("=" * 60)
        print("RULED OUT / SUPERSEDED HYPOTHESES")
        print("=" * 60)

        for row in rows:
            print(f"\n* {row['name']}")
            print(f"  Status: {row['status']}")
            if row['description']:
                print(f"  Description: {row['description']}")
            if row['ruled_out_reason']:
                print(f"  Why ruled out: {row['ruled_out_reason']}")
            if row['ruling_bibcode']:
                title = row['ruling_paper_title'] or row['ruling_bibcode']
                print(f"  Ruling paper: {title[:50]}...")
            if row['superseded_by']:
                print(f"  Superseded by: {row['superseded_by']}")
    return 0


# ============================================================================
# Export/Stats Commands
# ============================================================================

def export_data(args):
    """Export database data."""
    db = get_db()

    data = {
        'exported_at': datetime.now().isoformat(),
        'papers': [],
        'citations': [],
    }

    if args.session_id:
        # Export specific session
        cursor = db.execute(
            "SELECT * FROM research_sessions WHERE id = ?",
            (args.session_id,)
        )
        session = db.fetchone(cursor)

        if not session:
            print(f"Session {args.session_id} not found", file=sys.stderr)
            return 1

        data['session'] = dict(session)

        # Get session papers
        cursor = db.execute(
            "SELECT bibcode FROM session_papers WHERE session_id = ?",
            (args.session_id,)
        )
        bibcodes = db.fetchall(cursor)
        bibcode_list = [r['bibcode'] for r in bibcodes]

        if bibcode_list:
            placeholders = ','.join('?' * len(bibcode_list))
            cursor = db.execute(
                f"SELECT * FROM papers WHERE bibcode IN ({placeholders})",
                tuple(bibcode_list)
            )
            data['papers'] = db.fetchall(cursor)

            cursor = db.execute(f"""
                SELECT * FROM citations
                WHERE citing_bibcode IN ({placeholders})
                   OR cited_bibcode IN ({placeholders})
            """, tuple(bibcode_list + bibcode_list))
            data['citations'] = db.fetchall(cursor)
    else:
        # Export all
        cursor = db.execute("SELECT * FROM papers")
        data['papers'] = db.fetchall(cursor)

        cursor = db.execute("SELECT * FROM citations")
        data['citations'] = db.fetchall(cursor)

    if args.format == 'json':
        output = json.dumps(data, indent=2, default=str)
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
    db = get_db()

    cursor = db.execute("SELECT COUNT(*) as cnt FROM papers")
    paper_count = db.fetchone(cursor)['cnt']

    cursor = db.execute("SELECT COUNT(*) as cnt FROM citations")
    citation_count = db.fetchone(cursor)['cnt']

    cursor = db.execute("SELECT COUNT(*) as cnt FROM research_sessions")
    session_count = db.fetchone(cursor)['cnt']

    cursor = db.execute("SELECT COUNT(*) as cnt FROM hypotheses")
    hypothesis_count = db.fetchone(cursor)['cnt']

    print("=" * 50)
    print("LITERATURE DATABASE STATISTICS")
    print("=" * 50)
    print(f"Database: {db.get_db_path()}")
    print(f"Papers: {paper_count}")
    print(f"Citations: {citation_count}")
    print(f"Hypotheses: {hypothesis_count}")
    print(f"Sessions: {session_count}")

    if citation_count > 0:
        print("\nCitation breakdown:")
        cursor = db.execute("""
            SELECT classification, COUNT(*) as count
            FROM citations
            GROUP BY classification
            ORDER BY count DESC
        """)
        rows = db.fetchall(cursor)
        for row in rows:
            marker = " [!]" if row['classification'] == 'REFUTING' else ""
            print(f"  {row['classification']:15} {row['count']}{marker}")

    if hypothesis_count > 0:
        print("\nHypothesis status:")
        cursor = db.execute("""
            SELECT status, COUNT(*) as count
            FROM hypotheses
            GROUP BY status
        """)
        rows = db.fetchall(cursor)
        for row in rows:
            icon = {'ACTIVE': '+', 'RULED_OUT': 'x', 'SUPERSEDED': '>', 'UNCERTAIN': '?'}.get(row['status'], '')
            print(f"  {icon} {row['status']:15} {row['count']}")

    if paper_count > 0:
        print("\nTop cited papers in database:")
        cursor = db.execute("""
            SELECT bibcode, title, citation_count
            FROM papers
            ORDER BY citation_count DESC
            LIMIT 5
        """)
        rows = db.fetchall(cursor)
        for row in rows:
            title = row['title'][:40] + '...' if row['title'] and len(row['title']) > 40 else row['title']
            ccount = row['citation_count'] or 0
            print(f"  [{ccount:4}] {title}")

    # Show ruled out hypotheses summary
    cursor = db.execute("""
        SELECT COUNT(*) as cnt FROM hypotheses WHERE status = 'RULED_OUT'
    """)
    ruled_out = db.fetchone(cursor)['cnt']
    if ruled_out > 0:
        print(f"\n[!] {ruled_out} hypothesis(es) have been RULED OUT")
        print("   Run: litdb.py hypothesis ruled-out")

    return 0


def reset_db(args):
    """Reset (delete) the database."""
    from db_backend import SQLITE_DB_PATH

    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()

    if not args.confirm:
        print("Use --confirm to actually delete the database", file=sys.stderr)
        return 1

    if backend == 'postgresql':
        # For PostgreSQL, drop all tables
        db = get_db()
        tables = ['session_papers', 'hypothesis_papers', 'citations',
                  'hypotheses', 'research_sessions', 'papers']
        for table in tables:
            try:
                db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            except Exception:
                pass
        db.commit()
        print(f"Dropped all tables in PostgreSQL database")
    else:
        if SQLITE_DB_PATH.exists():
            SQLITE_DB_PATH.unlink()
            print(f"Deleted database: {SQLITE_DB_PATH}")
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
                       choices=['SUPPORTING', 'CONTRASTING', 'REFUTING',
                               'CONTEXTUAL', 'METHODOLOGICAL', 'NEUTRAL'],
                       help='Citation classification (REFUTING = definitively rules out)')
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

    # Hypothesis commands
    hyp_parser = subparsers.add_parser('hypothesis', help='Hypothesis/theory tracking')
    hyp_sub = hyp_parser.add_subparsers(dest='subcommand')

    h_add = hyp_sub.add_parser('add', help='Add a hypothesis')
    h_add.add_argument('--name', '-n', required=True, help='Hypothesis name')
    h_add.add_argument('--description', '-d', help='Description')
    h_add.add_argument('--status', '-s',
                       choices=['ACTIVE', 'RULED_OUT', 'SUPERSEDED', 'UNCERTAIN'],
                       default='UNCERTAIN', help='Current status')
    h_add.add_argument('--origin', help='Bibcode of originating paper')
    h_add.add_argument('--ruling', help='Bibcode of paper that ruled it out')
    h_add.add_argument('--reason', help='Why it was ruled out')
    h_add.add_argument('--superseded-by', help='Name of replacing hypothesis')
    h_add.set_defaults(func=hypothesis_add)

    h_list = hyp_sub.add_parser('list', help='List hypotheses')
    h_list.add_argument('--status', '-s', help='Filter by status')
    h_list.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    h_list.set_defaults(func=hypothesis_list)

    h_update = hyp_sub.add_parser('update', help='Update hypothesis status')
    h_update.add_argument('--id', type=int, required=True, help='Hypothesis ID')
    h_update.add_argument('--status', '-s',
                          choices=['ACTIVE', 'RULED_OUT', 'SUPERSEDED', 'UNCERTAIN'],
                          help='New status')
    h_update.add_argument('--ruling', help='Bibcode of ruling paper')
    h_update.add_argument('--reason', help='Reason for status change')
    h_update.add_argument('--superseded-by', help='Name of replacing hypothesis')
    h_update.set_defaults(func=hypothesis_update)

    h_link = hyp_sub.add_parser('link', help='Link paper to hypothesis')
    h_link.add_argument('--hypothesis-id', type=int, required=True, help='Hypothesis ID')
    h_link.add_argument('--bibcode', '-b', required=True, help='Paper bibcode')
    h_link.add_argument('--stance', required=True,
                        choices=['SUPPORTS', 'REFUTES', 'DISCUSSES', 'PROPOSES'],
                        help='Paper stance on hypothesis')
    h_link.set_defaults(func=hypothesis_link)

    h_ruled_out = hyp_sub.add_parser('ruled-out', help='List ruled-out hypotheses')
    h_ruled_out.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    h_ruled_out.set_defaults(func=hypothesis_ruled_out)

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
        elif args.command == 'hypothesis':
            hyp_parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
