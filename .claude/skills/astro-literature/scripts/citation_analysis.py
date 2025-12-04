#!/usr/bin/env python3
"""
Citation Network Analysis Script

Analyzes the citation network around a given paper, including:
- Papers that cite it
- Papers it references
- Co-citation analysis
- Bibliographic coupling
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

try:
    import ads
except ImportError:
    print("Error: 'ads' package not installed. Run: pip install ads", file=sys.stderr)
    sys.exit(1)


def get_token():
    """Get ADS API token from environment or file."""
    token = os.environ.get('ADS_DEV_KEY')
    if token:
        return token

    token_file = Path.home() / '.ads' / 'dev_key'
    if token_file.exists():
        return token_file.read_text().strip()

    return None


def get_paper_details(bibcode):
    """Get full details for a single paper."""
    fields = [
        'bibcode', 'title', 'author', 'year', 'pub', 'abstract',
        'citation_count', 'reference', 'citation', 'doi', 'keyword'
    ]

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
        'author_count': len(paper.author) if paper.author else 0,
        'year': paper.year,
        'publication': paper.pub,
        'abstract': paper.abstract,
        'citation_count': paper.citation_count or 0,
        'citations': paper.citation or [],
        'references': paper.reference or [],
        'keywords': paper.keyword[:10] if paper.keyword else [],
        'ads_url': f"https://ui.adsabs.harvard.edu/abs/{paper.bibcode}"
    }


def get_citing_papers(bibcode, rows=50):
    """Get papers that cite the given paper with their details."""
    fields = [
        'bibcode', 'title', 'author', 'year', 'pub', 'abstract',
        'citation_count', 'reference', 'keyword'
    ]

    papers = list(ads.SearchQuery(
        q=f"citations(bibcode:{bibcode})",
        fl=fields,
        sort='citation_count desc',
        rows=rows
    ))

    results = []
    for paper in papers:
        results.append({
            'bibcode': paper.bibcode,
            'title': paper.title[0] if paper.title else None,
            'authors': paper.author[:5] if paper.author else [],
            'year': paper.year,
            'publication': paper.pub,
            'abstract': paper.abstract,
            'citation_count': paper.citation_count or 0,
            'references': paper.reference or [],
            'keywords': paper.keyword[:5] if paper.keyword else []
        })

    return results


def get_referenced_papers(bibcode, rows=50):
    """Get papers referenced by the given paper."""
    fields = [
        'bibcode', 'title', 'author', 'year', 'pub', 'abstract',
        'citation_count', 'keyword'
    ]

    papers = list(ads.SearchQuery(
        q=f"references(bibcode:{bibcode})",
        fl=fields,
        sort='citation_count desc',
        rows=rows
    ))

    results = []
    for paper in papers:
        results.append({
            'bibcode': paper.bibcode,
            'title': paper.title[0] if paper.title else None,
            'authors': paper.author[:5] if paper.author else [],
            'year': paper.year,
            'publication': paper.pub,
            'abstract': paper.abstract,
            'citation_count': paper.citation_count or 0,
            'keywords': paper.keyword[:5] if paper.keyword else []
        })

    return results


def find_co_citations(bibcode, citing_papers):
    """
    Find papers that are frequently co-cited with the target paper.

    Co-citation: Two papers are co-cited when they are both cited by a third paper.
    """
    co_citation_counts = Counter()

    for citing_paper in citing_papers:
        refs = citing_paper.get('references', [])
        # Count other papers cited alongside our target
        for ref in refs:
            if ref != bibcode:
                co_citation_counts[ref] += 1

    # Return top co-cited papers
    return co_citation_counts.most_common(20)


def find_bibliographic_coupling(bibcode, target_refs, citing_papers):
    """
    Find papers with bibliographic coupling to the target.

    Bibliographic coupling: Two papers are coupled when they cite the same paper.
    """
    coupling_scores = Counter()

    for citing_paper in citing_papers:
        refs = set(citing_paper.get('references', []))
        shared_refs = refs.intersection(set(target_refs))
        if shared_refs:
            coupling_scores[citing_paper['bibcode']] = len(shared_refs)

    return coupling_scores.most_common(20)


def analyze_citation_network(bibcode, citing_limit=50, ref_limit=50):
    """
    Perform comprehensive citation network analysis.

    Returns a dictionary with:
    - target_paper: Details of the analyzed paper
    - citing_papers: Papers that cite it
    - referenced_papers: Papers it references
    - co_citations: Frequently co-cited papers
    - bibliographic_coupling: Papers with shared references
    - temporal_distribution: Citation counts by year
    - keyword_analysis: Common keywords in citing papers
    """
    print(f"Fetching details for {bibcode}...", file=sys.stderr)
    target = get_paper_details(bibcode)
    if not target:
        print(f"Paper {bibcode} not found", file=sys.stderr)
        return None

    print(f"Fetching citing papers...", file=sys.stderr)
    citing_papers = get_citing_papers(bibcode, rows=citing_limit)

    print(f"Fetching referenced papers...", file=sys.stderr)
    referenced_papers = get_referenced_papers(bibcode, rows=ref_limit)

    print(f"Analyzing citation network...", file=sys.stderr)

    # Temporal distribution of citations
    year_counts = Counter()
    for paper in citing_papers:
        if paper.get('year'):
            year_counts[paper['year']] += 1

    # Keyword analysis in citing papers
    keyword_counts = Counter()
    for paper in citing_papers:
        for kw in paper.get('keywords', []):
            keyword_counts[kw] += 1

    # Co-citation analysis
    co_citations = find_co_citations(bibcode, citing_papers)

    # Bibliographic coupling
    coupling = find_bibliographic_coupling(
        bibcode,
        target.get('references', []),
        citing_papers
    )

    return {
        'target_paper': target,
        'citing_papers': citing_papers,
        'cited_papers_count': len(citing_papers),
        'referenced_papers': referenced_papers,
        'references_count': len(referenced_papers),
        'co_citations': [
            {'bibcode': bc, 'count': count}
            for bc, count in co_citations
        ],
        'bibliographic_coupling': [
            {'bibcode': bc, 'shared_refs': count}
            for bc, count in coupling
        ],
        'temporal_distribution': dict(sorted(year_counts.items())),
        'top_keywords': keyword_counts.most_common(20)
    }


def format_summary(analysis):
    """Format analysis results as human-readable summary."""
    target = analysis['target_paper']

    lines = [
        "=" * 70,
        "CITATION NETWORK ANALYSIS",
        "=" * 70,
        "",
        f"Target Paper: {target['title']}",
        f"Authors: {', '.join(target['authors'][:3])}{'...' if len(target['authors']) > 3 else ''}",
        f"Year: {target['year']}",
        f"Publication: {target['publication']}",
        f"Total Citations: {target['citation_count']}",
        f"Total References: {len(target.get('references', []))}",
        "",
        "-" * 70,
        "TEMPORAL CITATION DISTRIBUTION",
        "-" * 70,
    ]

    for year, count in sorted(analysis['temporal_distribution'].items()):
        bar = '#' * min(count, 50)
        lines.append(f"  {year}: {bar} ({count})")

    lines.extend([
        "",
        "-" * 70,
        f"TOP CITING PAPERS ({len(analysis['citing_papers'])} analyzed)",
        "-" * 70,
    ])

    for i, paper in enumerate(analysis['citing_papers'][:10], 1):
        authors = paper['authors'][0] if paper['authors'] else 'Unknown'
        lines.append(f"  {i}. {paper['title'][:60]}...")
        lines.append(f"     {authors} et al. ({paper['year']}) - {paper['citation_count']} citations")

    lines.extend([
        "",
        "-" * 70,
        "TOP CO-CITED PAPERS",
        "-" * 70,
        "(Papers frequently cited alongside the target paper)",
    ])

    for item in analysis['co_citations'][:10]:
        lines.append(f"  {item['bibcode']}: {item['count']} times")

    lines.extend([
        "",
        "-" * 70,
        "KEYWORD THEMES IN CITING PAPERS",
        "-" * 70,
    ])

    for kw, count in analysis['top_keywords'][:15]:
        lines.append(f"  {kw}: {count}")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze citation network for an astronomical paper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --bibcode 2019ApJ...882L...2S
  %(prog)s --bibcode 2016PhRvL.116f1102A --citing-limit 100
  %(prog)s --bibcode 2011Natur.480..215K --format json --output network.json
        """
    )

    parser.add_argument('--bibcode', '-b', required=True,
                        help='ADS bibcode of the target paper')
    parser.add_argument('--citing-limit', type=int, default=50,
                        help='Max citing papers to analyze (default: 50)')
    parser.add_argument('--ref-limit', type=int, default=50,
                        help='Max referenced papers to retrieve (default: 50)')
    parser.add_argument('--format', '-f', choices=['json', 'summary'],
                        default='summary', help='Output format')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    args = parser.parse_args()

    # Check for API token
    token = get_token()
    if not token:
        print("Error: ADS API token not found.", file=sys.stderr)
        sys.exit(1)

    # Run analysis
    analysis = analyze_citation_network(
        args.bibcode,
        citing_limit=args.citing_limit,
        ref_limit=args.ref_limit
    )

    if not analysis:
        sys.exit(1)

    # Format output
    if args.format == 'json':
        output = json.dumps(analysis, indent=2)
    else:
        output = format_summary(analysis)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Analysis written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
