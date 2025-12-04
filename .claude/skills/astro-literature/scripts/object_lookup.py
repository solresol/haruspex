#!/usr/bin/env python3
"""
Astronomical Object Lookup Script

Query SIMBAD and NED for astronomical object information and bibliography.
Supports cross-referencing object identifiers and finding related papers.
"""

import argparse
import json
import sys

try:
    from astroquery.simbad import Simbad
    from astroquery.ipac.ned import Ned
    from astropy.coordinates import SkyCoord
    import astropy.units as u
except ImportError as e:
    print(f"Error: Required package not installed: {e}", file=sys.stderr)
    print("Run: pip install astroquery astropy", file=sys.stderr)
    sys.exit(1)


def query_simbad(object_name, include_refs=False):
    """
    Query SIMBAD for object information.

    Args:
        object_name: Name or identifier of the astronomical object
        include_refs: Whether to query for bibliographic references

    Returns:
        Dictionary with object data
    """
    try:
        # Basic object query
        result = Simbad.query_object(object_name)
        if result is None:
            return {'error': f"Object '{object_name}' not found in SIMBAD"}

        row = result[0]

        data = {
            'database': 'SIMBAD',
            'main_id': str(row['main_id']),
            'ra': float(row['ra']),
            'dec': float(row['dec']),
            'object_type': str(row['otype']),
        }

        # Get all identifiers
        ids_result = Simbad.query_objectids(object_name)
        if ids_result is not None:
            data['identifiers'] = [str(row['id']) for row in ids_result]

        # Get bibliographic references if requested
        if include_refs:
            try:
                bibcodes = Simbad.query_bibcode(f"object:{object_name}", wildcard=True)
                if bibcodes is not None:
                    data['bibcode_count'] = len(bibcodes)
                    data['sample_bibcodes'] = [str(row['bibcode']) for row in bibcodes[:20]]
            except Exception as e:
                data['bibliography_error'] = str(e)

        return data

    except Exception as e:
        return {'error': str(e)}


def query_ned(object_name, include_refs=False):
    """
    Query NED for object information.

    Args:
        object_name: Name or identifier of the astronomical object
        include_refs: Whether to query for bibliographic references

    Returns:
        Dictionary with object data
    """
    try:
        # Basic object query
        result = Ned.query_object(object_name)
        if result is None or len(result) == 0:
            return {'error': f"Object '{object_name}' not found in NED"}

        row = result[0]

        data = {
            'database': 'NED',
            'name': str(row['Object Name']),
            'ra': float(row['RA']),
            'dec': float(row['DEC']),
            'object_type': str(row['Type']),
            'redshift': float(row['Redshift']) if row['Redshift'] else None,
            'velocity': float(row['Velocity']) if row['Velocity'] else None,
        }

        # Get references if requested
        if include_refs:
            try:
                refs = Ned.get_table(object_name, table='references')
                if refs is not None:
                    data['reference_count'] = len(refs)
                    data['sample_references'] = []
                    for row in refs[:20]:
                        ref = {
                            'refcode': str(row['Refcode']) if 'Refcode' in row.colnames else None,
                            'title': str(row['Title']) if 'Title' in row.colnames else None,
                        }
                        data['sample_references'].append(ref)
            except Exception as e:
                data['bibliography_error'] = str(e)

        return data

    except Exception as e:
        return {'error': str(e)}


def query_region(ra, dec, radius_arcmin=5, database='simbad'):
    """
    Query for objects in a region of the sky.

    Args:
        ra: Right ascension in degrees
        dec: Declination in degrees
        radius_arcmin: Search radius in arcminutes
        database: 'simbad' or 'ned'

    Returns:
        List of objects in the region
    """
    coord = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
    radius = radius_arcmin * u.arcmin

    try:
        if database.lower() == 'simbad':
            result = Simbad.query_region(coord, radius=radius)
        else:
            result = Ned.query_region(coord, radius=radius)

        if result is None or len(result) == 0:
            return []

        objects = []
        for row in result:
            if database.lower() == 'simbad':
                obj = {
                    'id': str(row['main_id']),
                    'ra': float(row['ra']),
                    'dec': float(row['dec']),
                    'type': str(row['otype']),
                }
            else:
                obj = {
                    'name': str(row['Object Name']),
                    'ra': float(row['RA']),
                    'dec': float(row['DEC']),
                    'type': str(row['Type']),
                }
            objects.append(obj)

        return objects

    except Exception as e:
        return {'error': str(e)}


def cross_match(object_name):
    """
    Cross-match an object between SIMBAD and NED.

    Returns results from both databases for the same object.
    """
    simbad_result = query_simbad(object_name)
    ned_result = query_ned(object_name)

    return {
        'query': object_name,
        'simbad': simbad_result,
        'ned': ned_result,
        'match_status': 'both' if 'error' not in simbad_result and 'error' not in ned_result
                        else 'simbad_only' if 'error' not in simbad_result
                        else 'ned_only' if 'error' not in ned_result
                        else 'not_found'
    }


def format_output(data, format_type='json'):
    """Format results for output."""
    if format_type == 'json':
        return json.dumps(data, indent=2, default=str)

    elif format_type == 'summary':
        lines = []

        if isinstance(data, dict) and 'error' in data:
            return f"Error: {data['error']}"

        if 'simbad' in data:  # Cross-match result
            lines.append("=" * 60)
            lines.append(f"CROSS-MATCH RESULTS: {data['query']}")
            lines.append("=" * 60)
            lines.append(f"Match Status: {data['match_status']}")

            if 'error' not in data['simbad']:
                lines.extend([
                    "",
                    "--- SIMBAD ---",
                    f"Main ID: {data['simbad'].get('main_id')}",
                    f"RA/Dec: {data['simbad'].get('ra')}, {data['simbad'].get('dec')}",
                    f"Type: {data['simbad'].get('object_type')}",
                ])
                if data['simbad'].get('identifiers'):
                    lines.append(f"Identifiers: {', '.join(data['simbad']['identifiers'][:5])}")

            if 'error' not in data['ned']:
                lines.extend([
                    "",
                    "--- NED ---",
                    f"Name: {data['ned'].get('name')}",
                    f"RA/Dec: {data['ned'].get('ra')}, {data['ned'].get('dec')}",
                    f"Type: {data['ned'].get('object_type')}",
                    f"Redshift: {data['ned'].get('redshift')}",
                ])

        elif 'database' in data:  # Single database result
            db = data['database']
            lines.append("=" * 60)
            lines.append(f"{db} QUERY RESULT")
            lines.append("=" * 60)

            if db == 'SIMBAD':
                lines.extend([
                    f"Main ID: {data.get('main_id')}",
                    f"RA/Dec: {data.get('ra')}, {data.get('dec')}",
                    f"Type: {data.get('object_type')}",
                ])
                if data.get('identifiers'):
                    lines.append(f"Other identifiers: {len(data['identifiers'])}")
                    for ident in data['identifiers'][:10]:
                        lines.append(f"  - {ident}")
                if data.get('bibcode_count'):
                    lines.append(f"Bibliography: {data['bibcode_count']} references")

            elif db == 'NED':
                lines.extend([
                    f"Name: {data.get('name')}",
                    f"RA/Dec: {data.get('ra')}, {data.get('dec')}",
                    f"Type: {data.get('object_type')}",
                    f"Redshift: {data.get('redshift')}",
                    f"Velocity: {data.get('velocity')} km/s",
                ])
                if data.get('reference_count'):
                    lines.append(f"Bibliography: {data['reference_count']} references")

        elif isinstance(data, list):  # Region query result
            lines.append("=" * 60)
            lines.append(f"REGION QUERY: {len(data)} objects found")
            lines.append("=" * 60)
            for obj in data[:20]:
                name = obj.get('id') or obj.get('name')
                lines.append(f"  {name}: {obj.get('type')} at ({obj.get('ra'):.4f}, {obj.get('dec'):.4f})")

        return '\n'.join(lines)

    return json.dumps(data, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(
        description='Query astronomical databases for object information',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --object "M31" --database simbad
  %(prog)s --object "NGC 4151" --database ned --refs
  %(prog)s --object "Crab Nebula" --cross-match
  %(prog)s --ra 83.633 --dec 22.014 --radius 5 --database simbad
        """
    )

    parser.add_argument('--object', '-o', help='Object name or identifier')
    parser.add_argument('--database', '-d', choices=['simbad', 'ned'],
                        default='simbad', help='Database to query')
    parser.add_argument('--refs', action='store_true',
                        help='Include bibliographic references')
    parser.add_argument('--cross-match', action='store_true',
                        help='Query both SIMBAD and NED')
    parser.add_argument('--ra', type=float, help='Right ascension in degrees')
    parser.add_argument('--dec', type=float, help='Declination in degrees')
    parser.add_argument('--radius', type=float, default=5,
                        help='Search radius in arcminutes (default: 5)')
    parser.add_argument('--format', '-f', choices=['json', 'summary'],
                        default='summary', help='Output format')
    parser.add_argument('--output', help='Output file (default: stdout)')

    args = parser.parse_args()

    # Validate arguments
    if args.ra is not None and args.dec is not None:
        # Region query
        result = query_region(args.ra, args.dec, args.radius, args.database)
    elif args.object:
        if args.cross_match:
            result = cross_match(args.object)
        elif args.database == 'simbad':
            result = query_simbad(args.object, include_refs=args.refs)
        else:
            result = query_ned(args.object, include_refs=args.refs)
    else:
        parser.error("Either --object or --ra/--dec are required")

    # Format and output
    output = format_output(result, args.format)

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
