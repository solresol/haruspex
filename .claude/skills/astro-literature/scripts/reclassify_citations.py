#!/usr/bin/env python3
"""
Re-classify existing citations using the LLM-based classifier.

This script reads all citations from the database, fetches the abstracts
of both citing and cited papers, and re-classifies them using the LLM.

Usage:
    OPENAI_API_KEY=$(cat ~/.openai.key) python reclassify_citations.py [--dry-run]
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from db_backend import get_db, get_backend
from classify_citations import classify_with_llm, classify_by_patterns


def get_paper_abstract(db, bibcode: str) -> tuple:
    """Get paper title and abstract from database."""
    cursor = db.execute(
        "SELECT title, abstract FROM papers WHERE bibcode = ?",
        (bibcode,)
    )
    row = db.fetchone(cursor)
    if row:
        return row['title'], row['abstract']
    return None, None


def reclassify_all_citations(dry_run: bool = False, use_llm: bool = True):
    """Re-classify all citations in the database."""
    db = get_db()

    # Get all citations
    cursor = db.execute("""
        SELECT id, citing_bibcode, cited_bibcode, classification, confidence, reasoning
        FROM citations
        ORDER BY id
    """)
    citations = db.fetchall(cursor)

    print(f"Found {len(citations)} citations to re-classify")
    print(f"Using {'LLM' if use_llm else 'regex'} classifier")
    print(f"Dry run: {dry_run}")
    print("=" * 60)

    updated = 0
    unchanged = 0
    errors = 0

    for i, cit in enumerate(citations):
        citing_bibcode = cit['citing_bibcode']
        cited_bibcode = cit['cited_bibcode']
        old_classification = cit['classification']
        old_confidence = cit['confidence']

        # Get abstracts
        citing_title, citing_abstract = get_paper_abstract(db, citing_bibcode)
        cited_title, cited_abstract = get_paper_abstract(db, cited_bibcode)

        if not citing_abstract:
            print(f"[{i+1}/{len(citations)}] SKIP: No citing abstract for {citing_bibcode}")
            errors += 1
            continue

        try:
            if use_llm:
                new_classification, new_confidence, reasoning = classify_with_llm(
                    citing_abstract,
                    cited_abstract or "",
                    cited_title or ""
                )
                # Rate limit - OpenAI has rate limits
                time.sleep(0.5)
            else:
                new_classification, new_confidence, matched = classify_by_patterns(citing_abstract)
                reasoning = f"Regex patterns: {matched}" if matched else "No patterns matched"

            changed = new_classification != old_classification

            status = "CHANGED" if changed else "same"
            conf_change = f"{old_confidence or 0:.2f} -> {new_confidence:.2f}"

            print(f"[{i+1}/{len(citations)}] {status}: {citing_bibcode[:20]} -> {cited_bibcode[:20]}")
            if changed:
                print(f"    {old_classification} -> {new_classification} ({conf_change})")
                print(f"    Reason: {reasoning[:80]}...")

            if changed and not dry_run:
                # Update the database
                backend = os.environ.get('LITDB_BACKEND', 'sqlite').lower()
                if backend == 'postgresql':
                    db.execute("""
                        UPDATE citations
                        SET classification = %s, confidence = %s, reasoning = %s,
                            analyzed_at = %s, analyzed_by = %s
                        WHERE id = %s
                    """, (
                        new_classification,
                        new_confidence,
                        reasoning,
                        datetime.now().isoformat(),
                        'llm-reclassify' if use_llm else 'regex-reclassify',
                        cit['id']
                    ))
                else:
                    db.execute("""
                        UPDATE citations
                        SET classification = ?, confidence = ?, reasoning = ?,
                            analyzed_at = ?, analyzed_by = ?
                        WHERE id = ?
                    """, (
                        new_classification,
                        new_confidence,
                        reasoning,
                        datetime.now().isoformat(),
                        'llm-reclassify' if use_llm else 'regex-reclassify',
                        cit['id']
                    ))
                db.commit()
                updated += 1
            elif not changed:
                unchanged += 1

        except Exception as e:
            print(f"[{i+1}/{len(citations)}] ERROR: {citing_bibcode} -> {cited_bibcode}: {e}")
            errors += 1
            continue

    print("\n" + "=" * 60)
    print("RECLASSIFICATION COMPLETE")
    print("=" * 60)
    print(f"Total citations:  {len(citations)}")
    print(f"Updated:          {updated}")
    print(f"Unchanged:        {unchanged}")
    print(f"Errors/Skipped:   {errors}")

    if dry_run:
        print("\n(Dry run - no changes were saved)")


def main():
    parser = argparse.ArgumentParser(
        description='Re-classify citations using LLM-based classifier'
    )
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be changed without saving')
    parser.add_argument('--regex', action='store_true',
                        help='Use regex classifier instead of LLM')

    args = parser.parse_args()

    if not args.regex and not os.environ.get('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY=$(cat ~/.openai.key)")
        print("Or use --regex to use the regex-based classifier")
        sys.exit(1)

    reclassify_all_citations(dry_run=args.dry_run, use_llm=not args.regex)


if __name__ == '__main__':
    main()
