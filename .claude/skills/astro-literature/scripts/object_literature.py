#!/usr/bin/env python3
"""
Object-Centric Literature Analysis

Extract astronomical objects from papers, query SIMBAD for their bibliographies,
and produce per-object summaries of the state of the art.

This implements the "object-driven" approach to literature review:
  Research Question → Find review papers → Extract object names →
  Query SIMBAD for each object → Get ALL papers on that object →
  Summarize state-of-art per object → Synthesize back to topic
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from astroquery.simbad import Simbad
    import astropy.units as u
except ImportError:
    print("Error: astroquery not installed. Run: pip install astroquery", file=sys.stderr)
    sys.exit(1)

try:
    import ads
except ImportError:
    print("Error: ads package not installed. Run: pip install ads", file=sys.stderr)
    sys.exit(1)


# Common astronomical object patterns
OBJECT_PATTERNS = [
    # Named objects
    r'\b(HD\s*\d+[A-Za-z]?)\b',
    r'\b(HR\s*\d+)\b',
    r'\b(GJ\s*\d+[A-Za-z]?)\b',
    r'\b(HIP\s*\d+)\b',
    r'\b(TYC\s*\d+-\d+-\d+)\b',
    # Messier objects
    r'\b(M\s*\d{1,3})\b',
    # NGC/IC objects
    r'\b(NGC\s*\d+[A-Za-z]?)\b',
    r'\b(IC\s*\d+)\b',
    # Common named objects
    r'\b(HL\s*Tau(?:ri)?)\b',
    r'\b(TW\s*Hya(?:e)?)\b',
    r'\b(AS\s*\d+)\b',
    r'\b(PDS\s*\d+[A-Za-z]?)\b',
    r'\b(V\d{3,4}\s*[A-Za-z]+)\b',
    r'\b(AB\s*Aur(?:igae)?)\b',
    r'\b(MWC\s*\d+)\b',
    r'\b(LkCa\s*\d+)\b',
    r'\b(GM\s*Aur(?:igae)?)\b',
    r'\b(DM\s*Tau(?:ri)?)\b',
    r'\b(CQ\s*Tau(?:ri)?)\b',
    r'\b(UX\s*Tau(?:ri)?)\b',
    r'\b(GW\s*Lup(?:i)?)\b',
    r'\b(Elias\s*\d+-\d+)\b',
    r'\b(DoAr\s*\d+)\b',
    r'\b(SR\s*\d+)\b',
    r'\b(WSB\s*\d+)\b',
    r'\b(RNO\s*\d+)\b',
    r'\b(IRAS\s*\d+[+-]\d+)\b',
    # Exoplanet systems
    r'\b(Kepler-\d+[a-z]?)\b',
    r'\b(K2-\d+[a-z]?)\b',
    r'\b(TOI-\d+[a-z]?)\b',
    r'\b(TRAPPIST-\d+[a-z]?)\b',
    r'\b(WASP-\d+[a-z]?)\b',
    r'\b(HAT-P-\d+[a-z]?)\b',
    r'\b(CoRoT-\d+[a-z]?)\b',
    # 2MASS designations
    r'\b(2MASS\s*J?\d{8}[+-]\d{6,7})\b',
    # Disk-specific
    r'\b(Oph\s*\d+-\d+)\b',
    r'\b(Oph\s*IRS\s*\d+)\b',
    r'\b(WL\s*\d+)\b',
    r'\b(Haro\s*\d+-\d+)\b',
]


def extract_objects_from_text(text):
    """
    Extract astronomical object names from text (abstract, title, keywords).

    Returns a list of unique object names found.
    """
    if not text:
        return []

    objects = set()
    for pattern in OBJECT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Normalize spacing
            normalized = re.sub(r'\s+', ' ', match.strip())
            objects.add(normalized)

    return list(objects)


def extract_objects_from_paper(paper_data):
    """
    Extract object names from a paper's metadata.

    Args:
        paper_data: Dict with 'title', 'abstract', 'keywords' fields

    Returns:
        List of unique object names
    """
    all_text = ' '.join([
        paper_data.get('title', '') or '',
        paper_data.get('abstract', '') or '',
        ' '.join(paper_data.get('keywords', []) or [])
    ])

    return extract_objects_from_text(all_text)


def query_simbad_bibliography(object_name, max_refs=50):
    """
    Query SIMBAD for bibliographic references about an object.

    Returns list of bibcodes.
    """
    try:
        # Query for basic object info first
        result = Simbad.query_object(object_name)
        if result is None:
            return {'error': f"Object '{object_name}' not found in SIMBAD", 'bibcodes': []}

        main_id = str(result[0]['main_id'])

        # Query for bibliographic references
        # Note: SIMBAD bibliographic queries can be slow for well-studied objects
        try:
            # Use TAP query for bibliography
            from astroquery.simbad import Simbad as SimbadTAP
            custom_simbad = SimbadTAP()
            custom_simbad.add_votable_fields('bibcodelist(1990-2025)')
            bib_result = custom_simbad.query_object(object_name)

            if bib_result is not None and 'BIBCODELIST_1990_2025' in bib_result.colnames:
                bibcodes_str = str(bib_result[0]['BIBCODELIST_1990_2025'])
                if bibcodes_str and bibcodes_str != '--':
                    bibcodes = [b.strip() for b in bibcodes_str.split('|') if b.strip()]
                    return {
                        'main_id': main_id,
                        'bibcodes': bibcodes[:max_refs],
                        'total_count': len(bibcodes)
                    }
        except Exception as e:
            pass

        return {'main_id': main_id, 'bibcodes': [], 'error': 'Could not retrieve bibliography'}

    except Exception as e:
        return {'error': str(e), 'bibcodes': []}


def get_ads_metadata_for_bibcodes(bibcodes, max_papers=20):
    """
    Fetch ADS metadata for a list of bibcodes.
    """
    if not bibcodes:
        return []

    # Build query with multiple bibcodes
    bibcode_query = ' OR '.join([f'bibcode:{b}' for b in bibcodes[:max_papers]])

    fields = [
        'bibcode', 'title', 'author', 'year', 'pub',
        'abstract', 'citation_count', 'keyword'
    ]

    try:
        papers = ads.SearchQuery(
            q=bibcode_query,
            fl=fields,
            rows=max_papers
        )

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
                'keywords': paper.keyword[:10] if paper.keyword else []
            })

        return sorted(results, key=lambda x: x['citation_count'], reverse=True)

    except Exception as e:
        print(f"ADS query error: {e}", file=sys.stderr)
        return []


def search_ads_for_object(object_name, max_papers=20):
    """
    Search ADS directly for papers about an astronomical object.
    More reliable than SIMBAD bibliography for well-known objects.
    """
    # Escape quotes in object name for ADS query
    escaped_name = object_name.replace('"', '\\"')

    # Search in title and abstract (ADS doesn't have 'object' field)
    query = f'title:"{escaped_name}" OR abstract:"{escaped_name}"'

    fields = [
        'bibcode', 'title', 'author', 'year', 'pub',
        'abstract', 'citation_count', 'keyword', 'property'
    ]

    try:
        papers = ads.SearchQuery(
            q=query,
            fl=fields,
            rows=max_papers,
            sort='citation_count desc'
        )

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
                'keywords': paper.keyword[:10] if paper.keyword else [],
                'is_refereed': 'REFEREED' in (paper.property or [])
            })

        return results

    except Exception as e:
        print(f"ADS query error for {object_name}: {e}", file=sys.stderr)
        return []


def analyze_object_literature(object_name, max_papers=20):
    """
    Comprehensive analysis of literature about an astronomical object.

    Returns a dict with object info and paper summaries.
    """
    result = {
        'object_name': object_name,
        'simbad_id': None,
        'paper_count': 0,
        'papers': [],
        'top_topics': [],
        'errors': []
    }

    # Try SIMBAD for basic info
    try:
        simbad_result = Simbad.query_object(object_name)
        if simbad_result is not None:
            result['simbad_id'] = str(simbad_result[0]['main_id'])
    except Exception as e:
        pass  # Not critical if SIMBAD fails

    # Use ADS directly for papers (more reliable)
    papers = search_ads_for_object(object_name, max_papers=max_papers)
    result['papers'] = papers
    result['paper_count'] = len(papers)

    if not papers:
        result['errors'].append(f"No papers found for {object_name}")
        return result

    # Extract top topics from keywords
    all_keywords = []
    for paper in papers:
        all_keywords.extend(paper.get('keywords', []))

    # Count keyword frequency
    from collections import Counter
    keyword_counts = Counter(all_keywords)
    result['top_topics'] = [kw for kw, count in keyword_counts.most_common(10)]

    return result


def format_object_report(analysis):
    """Format analysis results as a readable report."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"OBJECT: {analysis['object_name']}")
    if analysis['simbad_id']:
        lines.append(f"SIMBAD ID: {analysis['simbad_id']}")
    lines.append(f"{'='*60}")

    if analysis['errors']:
        lines.append(f"Errors: {', '.join(analysis['errors'])}")
        return '\n'.join(lines)

    lines.append(f"Total papers in SIMBAD: {analysis['paper_count']}")
    lines.append(f"Papers analyzed: {len(analysis['papers'])}")

    if analysis['top_topics']:
        lines.append(f"\nTop research topics: {', '.join(analysis['top_topics'][:5])}")

    lines.append("\nMost-cited papers:")
    for i, paper in enumerate(analysis['papers'][:10], 1):
        authors = paper['authors'][0] if paper['authors'] else 'Unknown'
        if len(paper.get('authors', [])) > 1:
            authors += ' et al.'
        lines.append(f"\n{i}. {paper['title']}")
        lines.append(f"   {authors} ({paper['year']})")
        lines.append(f"   Citations: {paper['citation_count']}")
        lines.append(f"   Bibcode: {paper['bibcode']}")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Object-centric literature analysis for astronomy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --object "PDS 70"
  %(prog)s --object "HL Tau" --max-papers 30
  %(prog)s --extract-from-abstract "We observed the protoplanetary disk around HL Tau..."
  %(prog)s --from-paper /tmp/paper.json
        """
    )

    parser.add_argument('--object', '-o', help='Single object name to analyze')
    parser.add_argument('--objects', nargs='+', help='Multiple object names')
    parser.add_argument('--extract-from-abstract', help='Extract objects from text')
    parser.add_argument('--from-paper', help='Extract objects from paper JSON file')
    parser.add_argument('--max-papers', type=int, default=20,
                        help='Max papers to retrieve per object (default: 20)')
    parser.add_argument('--format', '-f', choices=['json', 'summary'],
                        default='summary', help='Output format')
    parser.add_argument('--output', help='Output file')

    args = parser.parse_args()

    objects_to_analyze = []

    if args.object:
        objects_to_analyze.append(args.object)

    if args.objects:
        objects_to_analyze.extend(args.objects)

    if args.extract_from_abstract:
        extracted = extract_objects_from_text(args.extract_from_abstract)
        objects_to_analyze.extend(extracted)
        print(f"Extracted objects: {extracted}", file=sys.stderr)

    if args.from_paper:
        with open(args.from_paper) as f:
            paper_data = json.load(f)
            if isinstance(paper_data, list):
                paper_data = paper_data[0]
            extracted = extract_objects_from_paper(paper_data)
            objects_to_analyze.extend(extracted)
            print(f"Extracted objects from paper: {extracted}", file=sys.stderr)

    if not objects_to_analyze:
        parser.error("No objects specified. Use --object, --objects, --extract-from-abstract, or --from-paper")

    # Remove duplicates while preserving order
    seen = set()
    unique_objects = []
    for obj in objects_to_analyze:
        if obj.lower() not in seen:
            seen.add(obj.lower())
            unique_objects.append(obj)

    # Analyze each object
    results = []
    for obj in unique_objects:
        print(f"Analyzing: {obj}...", file=sys.stderr)
        analysis = analyze_object_literature(obj, max_papers=args.max_papers)
        results.append(analysis)

    # Format output
    if args.format == 'json':
        output = json.dumps(results, indent=2, default=str)
    else:
        output = '\n'.join(format_object_report(r) for r in results)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
