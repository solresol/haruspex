#!/usr/bin/env python3
"""
ADS Paper Search Script

Search NASA ADS for astronomical papers using various query parameters.
Requires an ADS API token set via ADS_DEV_KEY environment variable
or stored in ~/.ads/dev_key
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import ads
except ImportError:
    print("Error: 'ads' package not installed. Run: pip install ads", file=sys.stderr)
    sys.exit(1)


def get_token():
    """Get ADS API token from environment or file."""
    # Check environment variable first
    token = os.environ.get('ADS_DEV_KEY')
    if token:
        return token

    # Check ~/.ads/dev_key file
    token_file = Path.home() / '.ads' / 'dev_key'
    if token_file.exists():
        return token_file.read_text().strip()

    return None


def search_papers(query, rows=20, sort='citation_count desc',
                  year_start=None, year_end=None, refereed_only=False):
    """
    Search ADS for papers matching the query.

    Args:
        query: ADS search query string
        rows: Number of results to return (max 2000)
        sort: Sort order (e.g., 'citation_count desc', 'date desc')
        year_start: Start year for date range filter
        year_end: End year for date range filter
        refereed_only: Only return refereed publications

    Returns:
        List of paper dictionaries with metadata
    """
    # Build the query
    full_query = query

    if year_start and year_end:
        full_query += f" year:{year_start}-{year_end}"
    elif year_start:
        full_query += f" year:{year_start}-"
    elif year_end:
        full_query += f" year:-{year_end}"

    if refereed_only:
        full_query += " property:refereed"

    # Fields to retrieve
    fields = [
        'bibcode',
        'title',
        'author',
        'year',
        'pub',
        'abstract',
        'citation_count',
        'reference',
        'citation',
        'doi',
        'identifier',
        'keyword',
        'aff',
        'property'
    ]

    try:
        papers = ads.SearchQuery(
            q=full_query,
            fl=fields,
            sort=sort,
            rows=rows
        )

        results = []
        for paper in papers:
            paper_dict = {
                'bibcode': paper.bibcode,
                'title': paper.title[0] if paper.title else None,
                'authors': paper.author[:10] if paper.author else [],  # Limit to first 10
                'author_count': len(paper.author) if paper.author else 0,
                'year': paper.year,
                'publication': paper.pub,
                'abstract': paper.abstract,
                'citation_count': paper.citation_count or 0,
                'reference_count': len(paper.reference) if paper.reference else 0,
                'doi': paper.doi[0] if paper.doi else None,
                'keywords': paper.keyword[:10] if paper.keyword else [],
                'is_refereed': 'REFEREED' in (paper.property or []),
                'ads_url': f"https://ui.adsabs.harvard.edu/abs/{paper.bibcode}"
            }
            results.append(paper_dict)

        return results

    except ads.exceptions.APIResponseError as e:
        print(f"ADS API Error: {e}", file=sys.stderr)
        return []


def get_citations(bibcode, rows=100):
    """Get papers that cite the given paper."""
    query = f"citations(bibcode:{bibcode})"
    return search_papers(query, rows=rows, sort='citation_count desc')


def get_references(bibcode, rows=100):
    """Get papers referenced by the given paper."""
    query = f"references(bibcode:{bibcode})"
    return search_papers(query, rows=rows, sort='citation_count desc')


def get_trending(topic=None, rows=20):
    """
    Get trending papers - papers getting unusual attention recently.

    The trending() operator finds papers with recent citation activity
    that exceeds expectations based on their age and field.
    """
    if topic:
        query = f"trending({topic})"
    else:
        query = "trending()"
    return search_papers(query, rows=rows, sort='score desc')


def get_useful(topic=None, rows=20):
    """
    Get papers marked as 'useful' by ADS readers.

    The useful() operator finds papers that users have marked as useful,
    which can surface important papers that citations alone might miss.
    """
    if topic:
        query = f"useful({topic})"
    else:
        query = "useful()"
    return search_papers(query, rows=rows, sort='score desc')


def get_reviews(topic=None, rows=20, year_start=None):
    """
    Get review articles on a topic.

    Searches Annual Review of Astronomy & Astrophysics (ARA&A),
    Space Science Reviews, and other review publications.
    """
    # Review journal bibstems and doctype
    review_filter = '(bibstem:"ARA&A" OR bibstem:"SSRv" OR bibstem:"AREPS" OR bibstem:"RvMP" OR doctype:review)'

    if topic:
        query = f'({topic}) AND {review_filter}'
    else:
        query = review_filter

    if year_start:
        query += f" year:{year_start}-"

    return search_papers(query, rows=rows, sort='citation_count desc')


def get_proposals(telescope=None, topic=None, rows=20, year_start=None):
    """
    Get telescope observing proposals (abstracts are public on ADS).

    This surfaces the 'zeitgeist' - what topics are fundable and
    observationally tractable right now.

    Args:
        telescope: 'hst', 'jwst', 'alma', 'chandra', or None for all
        topic: Optional topic to filter by
        rows: Number of results
        year_start: Start year filter
    """
    # Proposal bibstems by telescope
    telescope_bibstems = {
        'hst': 'hst..prop',
        'jwst': 'jwst.prop',
        'alma': 'alma.prop',
        'chandra': 'cxo..prop',
        'xmm': 'xmm..prop',
        'spitzer': 'sptz.prop',
    }

    if telescope and telescope.lower() in telescope_bibstems:
        bibstem = telescope_bibstems[telescope.lower()]
        query = f'bibstem:"{bibstem}"'
    else:
        # All major space telescope proposals
        all_props = ' OR '.join(f'bibstem:"{bs}"' for bs in telescope_bibstems.values())
        query = f'({all_props})'

    if topic:
        query = f'({topic}) AND {query}'

    if year_start:
        query += f" year:{year_start}-"

    return search_papers(query, rows=rows, sort='date desc')


def format_output(results, format_type='json'):
    """Format results for output."""
    if format_type == 'json':
        return json.dumps(results, indent=2)

    elif format_type == 'summary':
        lines = []
        for i, paper in enumerate(results, 1):
            authors = paper['authors'][0] if paper['authors'] else 'Unknown'
            if paper['author_count'] > 1:
                authors += f" et al. ({paper['author_count']} authors)"

            lines.append(f"\n{i}. {paper['title']}")
            lines.append(f"   {authors} ({paper['year']})")
            lines.append(f"   {paper['publication']}")
            lines.append(f"   Citations: {paper['citation_count']}")
            lines.append(f"   Bibcode: {paper['bibcode']}")

            if paper['abstract']:
                abstract = paper['abstract'][:300]
                if len(paper['abstract']) > 300:
                    abstract += "..."
                lines.append(f"   Abstract: {abstract}")

        return '\n'.join(lines)

    elif format_type == 'bibcodes':
        return '\n'.join(p['bibcode'] for p in results)

    return json.dumps(results, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description='Search NASA ADS for astronomical papers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --query "dark matter halo"
  %(prog)s --query "author:Riess" --year-start 2020
  %(prog)s --query 'title:"gravitational waves"' --refereed
  %(prog)s --citations 2019ApJ...882L...2S
  %(prog)s --references 2021ApJ...919..138Z
  %(prog)s --trending "protoplanetary disk"
  %(prog)s --reviews "planet formation" --year-start 2020
  %(prog)s --proposals --telescope jwst --topic "protoplanet"
        """
    )

    parser.add_argument('--query', '-q', help='ADS search query')
    parser.add_argument('--citations', help='Get papers citing this bibcode')
    parser.add_argument('--references', help='Get papers referenced by this bibcode')
    parser.add_argument('--trending', nargs='?', const='', metavar='TOPIC',
                        help='Get trending papers (optionally filtered by topic)')
    parser.add_argument('--useful', nargs='?', const='', metavar='TOPIC',
                        help='Get papers marked useful by readers')
    parser.add_argument('--reviews', nargs='?', const='', metavar='TOPIC',
                        help='Get review articles (ARA&A, SSRv, etc.)')
    parser.add_argument('--proposals', action='store_true',
                        help='Search telescope observing proposals')
    parser.add_argument('--telescope', choices=['hst', 'jwst', 'alma', 'chandra', 'xmm', 'spitzer'],
                        help='Filter proposals by telescope')
    parser.add_argument('--topic', help='Topic filter for proposals/trending/reviews')
    parser.add_argument('--rows', '-n', type=int, default=20,
                        help='Number of results (default: 20, max: 2000)')
    parser.add_argument('--sort', '-s', default='citation_count desc',
                        help='Sort order (default: citation_count desc)')
    parser.add_argument('--year-start', type=int, help='Start year filter')
    parser.add_argument('--year-end', type=int, help='End year filter')
    parser.add_argument('--refereed', action='store_true',
                        help='Only refereed publications')
    parser.add_argument('--format', '-f', choices=['json', 'summary', 'bibcodes'],
                        default='summary', help='Output format (default: summary)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    args = parser.parse_args()

    # Check for API token
    token = get_token()
    if not token:
        print("Error: ADS API token not found.", file=sys.stderr)
        print("Set ADS_DEV_KEY environment variable or create ~/.ads/dev_key",
              file=sys.stderr)
        sys.exit(1)

    # Must provide one of the search modes
    search_modes = [args.query, args.citations, args.references,
                    args.trending is not None, args.useful is not None,
                    args.reviews is not None, args.proposals]
    if not any(search_modes):
        parser.error("One of --query, --citations, --references, --trending, --useful, --reviews, or --proposals is required")

    # Execute search
    if args.citations:
        results = get_citations(args.citations, args.rows)
    elif args.references:
        results = get_references(args.references, args.rows)
    elif args.trending is not None:
        topic = args.trending or args.topic
        results = get_trending(topic=topic, rows=args.rows)
    elif args.useful is not None:
        topic = args.useful or args.topic
        results = get_useful(topic=topic, rows=args.rows)
    elif args.reviews is not None:
        topic = args.reviews or args.topic
        results = get_reviews(topic=topic, rows=args.rows, year_start=args.year_start)
    elif args.proposals:
        results = get_proposals(
            telescope=args.telescope,
            topic=args.topic,
            rows=args.rows,
            year_start=args.year_start
        )
    else:
        results = search_papers(
            args.query,
            rows=args.rows,
            sort=args.sort,
            year_start=args.year_start,
            year_end=args.year_end,
            refereed_only=args.refereed
        )

    # Format output
    output = format_output(results, args.format)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Print summary to stderr
    print(f"\nFound {len(results)} papers", file=sys.stderr)


if __name__ == '__main__':
    main()
