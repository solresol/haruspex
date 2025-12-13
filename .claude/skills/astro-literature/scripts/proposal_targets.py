#!/usr/bin/env python3
"""
Proposal Target Generator

Find understudied analogs to well-studied benchmark systems.
Useful for identifying observing proposal targets.

The key insight: Well-studied systems reveal what's scientifically interesting.
Similar but understudied systems are where new discoveries await.
"""

import argparse
import json
import sys
from collections import defaultdict

try:
    from astroquery.simbad import Simbad
    from astropy.coordinates import SkyCoord
    import astropy.units as u
except ImportError:
    print("Error: astroquery/astropy not installed", file=sys.stderr)
    sys.exit(1)

try:
    import ads
except ImportError:
    print("Error: ads package not installed", file=sys.stderr)
    sys.exit(1)


def get_object_info(object_name):
    """Get basic info about an object from SIMBAD."""
    custom_simbad = Simbad()
    custom_simbad.add_votable_fields('otype', 'sp_type')

    result = custom_simbad.query_object(object_name)
    if result is None:
        return None

    row = result[0]
    return {
        'name': object_name,
        'main_id': str(row['main_id']),
        'ra': float(row['ra']),
        'dec': float(row['dec']),
        'otype': str(row['otype']) if row['otype'] else None,
        'sp_type': str(row['sp_type']) if row['sp_type'] else None,
        'vmag': None,  # Skip flux fields due to API changes
        'kmag': None,
    }


def get_paper_count(object_name, recent_only=False):
    """
    Get paper count for an object from ADS.

    Args:
        object_name: Name to search
        recent_only: If True, only count papers from last 5 years
    """
    # Clean up object name for query
    clean_name = object_name.replace('*', '').strip()

    query = f'title:"{clean_name}" OR abstract:"{clean_name}"'
    if recent_only:
        query += ' year:2020-2025'

    try:
        papers = ads.SearchQuery(
            q=query,
            fl=['bibcode'],
            rows=500
        )
        count = len(list(papers))
        return count
    except Exception as e:
        print(f"  Warning: Could not get paper count for {object_name}: {e}", file=sys.stderr)
        return 0


def find_similar_by_region(benchmark_info, radius_deg=10, object_types=None):
    """
    Find similar objects in a region around the benchmark.

    Args:
        benchmark_info: Dict with ra, dec from get_object_info
        radius_deg: Search radius in degrees
        object_types: List of SIMBAD object types to include (e.g., ['TT*', 'Or*'])
    """
    if object_types is None:
        # Default: young stellar objects
        object_types = ['TT*', 'Or*', 'Ae*', 'Be*', 'Y*O']

    coord = SkyCoord(ra=benchmark_info['ra']*u.deg,
                     dec=benchmark_info['dec']*u.deg,
                     frame='icrs')

    custom_simbad = Simbad()
    custom_simbad.add_votable_fields('otype', 'sp_type')

    try:
        result = custom_simbad.query_region(coord, radius=radius_deg*u.deg)
    except Exception as e:
        print(f"SIMBAD query error: {e}", file=sys.stderr)
        return []

    if result is None:
        return []

    similar = []
    for row in result:
        otype = str(row['otype']) if row['otype'] else ''

        # Check if object type matches any of our target types
        matches_type = any(ot in otype for ot in object_types)
        if not matches_type:
            continue

        obj = {
            'name': str(row['main_id']),
            'ra': float(row['ra']),
            'dec': float(row['dec']),
            'otype': otype,
            'sp_type': str(row['sp_type']) if row['sp_type'] else None,
            'vmag': None,
            'kmag': None,
        }
        similar.append(obj)

    return similar


def find_similar_by_type(benchmark_info, search_limit=100):
    """
    Find similar objects by object type (TAP query).

    This is a broader search not limited by region.
    """
    otype = benchmark_info.get('otype', 'TT*')

    # For now, just return empty - TAP queries are complex
    # This would be implemented with SIMBAD TAP service
    return []


def analyze_study_depth(objects, max_to_check=50):
    """
    Analyze how well each object has been studied.

    Args:
        objects: List of object dicts from find_similar_*
        max_to_check: Maximum objects to query ADS for
    """
    results = []

    for i, obj in enumerate(objects[:max_to_check]):
        print(f"  Checking {i+1}/{min(len(objects), max_to_check)}: {obj['name']}...",
              file=sys.stderr, end='\r')

        total_papers = get_paper_count(obj['name'])
        recent_papers = get_paper_count(obj['name'], recent_only=True)

        obj['paper_count'] = total_papers
        obj['recent_papers'] = recent_papers
        obj['study_score'] = total_papers + 2 * recent_papers  # Weight recent work

        results.append(obj)

    print(" " * 60, file=sys.stderr, end='\r')  # Clear progress line
    return results


def rank_proposal_candidates(objects, benchmark_papers, max_papers=50, min_papers=1):
    """
    Rank objects by proposal potential (understudied but interesting).

    Args:
        objects: List with paper_count added
        benchmark_papers: Paper count for benchmark (for comparison)
        max_papers: Max papers to be considered "understudied"
        min_papers: Min papers (to filter out completely unknown objects)
    """
    candidates = []

    for obj in objects:
        papers = obj.get('paper_count', 0)

        # Filter by study depth
        if papers < min_papers or papers > max_papers:
            continue

        # Calculate proposal score
        # Lower papers = higher score (more understudied)
        # But having SOME papers is good (known to be interesting)
        if papers > 0:
            understudied_score = 1.0 / papers
        else:
            understudied_score = 0

        # Bonus for recent activity (someone thinks it's interesting)
        recent_bonus = min(obj.get('recent_papers', 0) / 5, 1.0)

        # Penalty if too faint (hard to observe)
        brightness_penalty = 0
        if obj.get('vmag') and obj['vmag'] > 15:
            brightness_penalty = 0.5

        proposal_score = understudied_score + recent_bonus - brightness_penalty
        obj['proposal_score'] = proposal_score
        obj['comparison_ratio'] = benchmark_papers / papers if papers > 0 else float('inf')

        candidates.append(obj)

    # Sort by proposal score (higher = better candidate)
    return sorted(candidates, key=lambda x: x['proposal_score'], reverse=True)


def format_output(benchmark, candidates, format_type='summary'):
    """Format results for output."""

    if format_type == 'json':
        return json.dumps({
            'benchmark': benchmark,
            'candidates': candidates
        }, indent=2, default=str)

    lines = []
    lines.append("=" * 70)
    lines.append(f"PROPOSAL TARGET CANDIDATES")
    lines.append(f"Benchmark: {benchmark['name']} ({benchmark.get('paper_count', '?')} papers)")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Understudied analogs that could be proposal targets:")
    lines.append("")

    for i, obj in enumerate(candidates[:20], 1):
        lines.append(f"{i}. {obj['name']}")
        lines.append(f"   Type: {obj['otype']}, SpType: {obj.get('sp_type', 'unknown')}")
        lines.append(f"   Papers: {obj['paper_count']} total, {obj.get('recent_papers', 0)} recent")
        lines.append(f"   Comparison: {obj.get('comparison_ratio', 0):.0f}x less studied than benchmark")
        if obj.get('vmag'):
            lines.append(f"   V mag: {obj['vmag']:.1f}")
        lines.append(f"   Coords: {obj['ra']:.4f}, {obj['dec']:.4f}")
        lines.append("")

    if format_type == 'proposal':
        lines.append("-" * 70)
        lines.append("PROPOSAL JUSTIFICATION TEMPLATE")
        lines.append("-" * 70)
        lines.append("")
        lines.append(f"The {benchmark['name']} system has been extensively studied ")
        lines.append(f"({benchmark.get('paper_count', 'many')} publications), revealing [key insights].")
        lines.append("")
        lines.append("We propose to observe the following understudied analogs:")
        lines.append("")
        for obj in candidates[:5]:
            lines.append(f"- {obj['name']}: Similar {obj['otype']} with only {obj['paper_count']} papers")
        lines.append("")
        lines.append("These observations would test whether [science question] by [method].")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Find understudied analogs for observing proposals',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --benchmark "PDS 70" --radius 20
  %(prog)s --benchmark "HL Tau" --radius 10 --max-papers 30
  %(prog)s --benchmark "TW Hya" --format proposal
        """
    )

    parser.add_argument('--benchmark', '-b', required=True,
                        help='Well-studied system to find analogs for')
    parser.add_argument('--radius', '-r', type=float, default=15,
                        help='Search radius in degrees (default: 15)')
    parser.add_argument('--max-papers', type=int, default=50,
                        help='Maximum papers for "understudied" (default: 50)')
    parser.add_argument('--min-papers', type=int, default=1,
                        help='Minimum papers (filter unknowns) (default: 1)')
    parser.add_argument('--object-types', nargs='+', default=['TT*', 'Or*'],
                        help='SIMBAD object types to search (default: TT* Or*)')
    parser.add_argument('--format', '-f', choices=['summary', 'json', 'proposal'],
                        default='summary', help='Output format')
    parser.add_argument('--output', '-o', help='Output file')

    args = parser.parse_args()

    # Get benchmark info
    print(f"Getting info for benchmark: {args.benchmark}...", file=sys.stderr)
    benchmark = get_object_info(args.benchmark)
    if benchmark is None:
        print(f"Error: Could not find {args.benchmark} in SIMBAD", file=sys.stderr)
        sys.exit(1)

    benchmark['paper_count'] = get_paper_count(args.benchmark)
    print(f"  Found: {benchmark['main_id']} ({benchmark['paper_count']} papers)", file=sys.stderr)

    # Find similar objects
    print(f"Searching for similar objects within {args.radius}°...", file=sys.stderr)
    similar = find_similar_by_region(benchmark, args.radius, args.object_types)
    print(f"  Found {len(similar)} candidates", file=sys.stderr)

    if not similar:
        print("No similar objects found. Try increasing --radius or changing --object-types",
              file=sys.stderr)
        sys.exit(1)

    # Analyze study depth
    print("Analyzing study depth (querying ADS)...", file=sys.stderr)
    analyzed = analyze_study_depth(similar)

    # Rank candidates
    candidates = rank_proposal_candidates(
        analyzed,
        benchmark['paper_count'],
        max_papers=args.max_papers,
        min_papers=args.min_papers
    )
    print(f"  Found {len(candidates)} understudied candidates", file=sys.stderr)

    # Output
    output = format_output(benchmark, candidates, args.format)

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
