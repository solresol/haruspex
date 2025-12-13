#!/usr/bin/env python3
"""
Fetch missing abstracts from NASA ADS.

This script finds papers in the database that are missing abstracts
and fetches them from ADS.

Requires ADS_DEV_KEY environment variable or ~/.ads/dev_key file.
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    import ads
except ImportError:
    print("Error: 'ads' package not installed. Run: pip install ads", file=sys.stderr)
    sys.exit(1)

from db_backend import get_db, json_serialize


def get_ads_token():
    """Get ADS API token from environment or file."""
    token = os.environ.get('ADS_DEV_KEY')
    if token:
        return token

    token_file = Path.home() / '.ads' / 'dev_key'
    if token_file.exists():
        return token_file.read_text().strip()

    return None


def fetch_paper_from_ads(bibcode: str) -> dict:
    """Fetch paper metadata from ADS by bibcode."""
    fields = [
        'bibcode',
        'title',
        'author',
        'year',
        'pub',
        'abstract',
        'citation_count',
        'reference',
        'doi',
        'keyword',
    ]

    try:
        papers = list(ads.SearchQuery(
            q=f"bibcode:{bibcode}",
            fl=fields,
            rows=1
        ))

        if not papers:
            return None

        paper = papers[0]
        return {
            'bibcode': paper.bibcode,
            'title': paper.title[0] if paper.title else None,
            'authors': paper.author[:10] if paper.author else [],
            'year': paper.year,
            'publication': paper.pub,
            'abstract': paper.abstract,
            'citation_count': paper.citation_count or 0,
            'reference_count': len(paper.reference) if paper.reference else 0,
            'doi': paper.doi[0] if paper.doi else None,
            'keywords': paper.keyword[:10] if paper.keyword else [],
            'ads_url': f"https://ui.adsabs.harvard.edu/abs/{paper.bibcode}"
        }

    except Exception as e:
        print(f"  Error fetching {bibcode}: {e}", file=sys.stderr)
        return None


def get_missing_bibcodes(db) -> list:
    """Get bibcodes that are missing abstracts."""
    # Get all unique bibcodes from citations that need abstracts
    cursor = db.execute('''
        SELECT DISTINCT c.citing_bibcode as bibcode
        FROM citations c
        LEFT JOIN papers p ON c.citing_bibcode = p.bibcode
        WHERE p.abstract IS NULL OR p.abstract = ''
        UNION
        SELECT DISTINCT c.cited_bibcode as bibcode
        FROM citations c
        LEFT JOIN papers p ON c.cited_bibcode = p.bibcode
        WHERE p.abstract IS NULL OR p.abstract = ''
    ''')
    rows = db.fetchall(cursor)
    return [row['bibcode'] for row in rows]


def update_paper_in_db(db, paper_data: dict):
    """Update or insert paper in database."""
    backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()

    if backend == 'postgresql':
        query = '''
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
        '''
    else:
        query = '''
            INSERT OR REPLACE INTO papers
            (bibcode, title, authors, year, publication, abstract, doi, ads_url,
             citation_count, reference_count, keywords, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''

    db.execute(query, (
        paper_data['bibcode'],
        paper_data['title'],
        json_serialize(paper_data['authors']),
        paper_data['year'],
        paper_data['publication'],
        paper_data['abstract'],
        paper_data['doi'],
        paper_data['ads_url'],
        paper_data['citation_count'],
        paper_data['reference_count'],
        json_serialize(paper_data['keywords']),
        datetime.now().isoformat()
    ))
    db.commit()


def main():
    # Check for ADS token
    token = get_ads_token()
    if not token:
        print("Error: ADS API token not found.", file=sys.stderr)
        print("Set ADS_DEV_KEY environment variable or create ~/.ads/dev_key",
              file=sys.stderr)
        sys.exit(1)

    db = get_db()

    # Get bibcodes missing abstracts
    missing = get_missing_bibcodes(db)
    print(f"Found {len(missing)} papers missing abstracts")
    print("=" * 60)

    fetched = 0
    failed = 0
    already_has_abstract = 0

    for i, bibcode in enumerate(missing):
        print(f"[{i+1}/{len(missing)}] Fetching {bibcode}...", end=" ")

        paper_data = fetch_paper_from_ads(bibcode)

        if paper_data is None:
            print("NOT FOUND")
            failed += 1
            continue

        if not paper_data['abstract']:
            print("NO ABSTRACT in ADS")
            failed += 1
            continue

        # Update database
        update_paper_in_db(db, paper_data)
        abstract_preview = paper_data['abstract'][:60] + "..." if len(paper_data['abstract']) > 60 else paper_data['abstract']
        print(f"OK - {abstract_preview}")
        fetched += 1

        # Rate limiting - ADS has rate limits
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print("FETCH COMPLETE")
    print("=" * 60)
    print(f"Total missing:    {len(missing)}")
    print(f"Fetched:          {fetched}")
    print(f"Failed/No abstract: {failed}")


if __name__ == '__main__':
    main()
