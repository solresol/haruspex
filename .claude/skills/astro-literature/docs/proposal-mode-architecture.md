# Proposal Generation Mode: Architecture Design

## The Reviewer's Insight

> "One simple thing that you could make this do is generate a list of potential observing proposals from objects similar to those targets, which might have been studied a bit but not in such depth..."

This is a powerful idea: **use the literature to identify understudied analogs to well-studied benchmark systems**.

---

## Core Concept

**Input**: A well-studied system (e.g., "PDS 70")
**Output**: List of similar but understudied systems that could be proposal targets

```
PDS 70 (648 papers)
    ↓ "find similar"
Similar systems by properties:
    - Same object type (T Tauri with disk)
    - Similar age (~5 Myr)
    - Similar distance (observable)
    - Has disk substructure
    ↓ "filter by study depth"
Understudied analogs:
    - System X: 12 papers (vs 648 for PDS 70)
    - System Y: 8 papers
    - System Z: 3 papers ← HIGH PRIORITY TARGET
```

---

## Architecture

### Module 1: Benchmark System Profiler

**Purpose**: Extract key properties from a well-studied system

```python
def profile_benchmark(object_name):
    """
    Extract properties that define what makes an object
    interesting for comparison.

    Returns:
        {
            'name': 'PDS 70',
            'object_type': 'T Tauri*',
            'spectral_type': 'K7',
            'distance_pc': 113,
            'age_myr': 5.4,
            'disk_type': 'transition',
            'has_gap': True,
            'has_planet': True,
            'paper_count': 648,
            'key_properties': ['accreting protoplanet', 'CPD'],
            'coordinates': (ra, dec),
            'region': 'Scorpius-Centaurus'
        }
    """
```

**Data sources**:
- SIMBAD for basic properties (coords, spectral type, object type)
- ADS for paper count
- Hardcoded knowledge for special properties (disk type, planets)

### Module 2: Analog Finder

**Purpose**: Find objects with similar properties

```python
def find_analogs(benchmark_profile, search_params):
    """
    Query SIMBAD for similar objects.

    Search strategies:
    1. Same object type + nearby in sky (cone search)
    2. Same object type + same star-forming region
    3. Same spectral type range + disk indicators
    4. Same age range (if known)

    Returns list of candidate analogs.
    """
```

**SIMBAD query approaches**:

```sql
-- By object type in same region
SELECT main_id, ra, dec, otype, sp_type
FROM basic
WHERE otype = 'TT*'  -- T Tauri stars
  AND CONTAINS(POINT('ICRS', ra, dec),
               CIRCLE('ICRS', 239.17, -22.36, 10))  -- 10 deg around Sco-Cen

-- By spectral type with disk indicator
SELECT main_id FROM basic
WHERE sp_type LIKE 'K%' OR sp_type LIKE 'M%'
  AND otype IN ('TT*', 'Or*', 'Ae*')
```

### Module 3: Study Depth Analyzer

**Purpose**: Count how well each analog has been studied

```python
def get_study_depth(object_name):
    """
    Quantify how well an object has been studied.

    Metrics:
    - Total paper count (from ADS)
    - Recent paper count (last 5 years)
    - High-impact paper count (>50 citations)
    - Has disk resolved? (keyword search)
    - Has ALMA observations? (bibstem search)
    - Has JWST observations? (proposal search)

    Returns study_depth_score and breakdown.
    """
```

### Module 4: Proposal Candidate Ranker

**Purpose**: Score and rank understudied analogs by proposal potential

```python
def rank_proposal_candidates(analogs, benchmark):
    """
    Score each analog for proposal potential.

    Scoring factors:
    + Similar to benchmark (property match)
    + Observable (declination, brightness)
    + Understudied (low paper count)
    + Scientifically interesting (disk indicators)
    + Timely (not recently observed by JWST/ALMA)

    Returns ranked list with justifications.
    """
```

### Module 5: Proposal Generator

**Purpose**: Generate proposal-ready target descriptions

```python
def generate_proposal_text(candidate, benchmark, science_case):
    """
    Generate text suitable for telescope proposal.

    Template:
    "The [benchmark] system has revealed [key insight].
     [Candidate] is a similar [type] at [distance] with
     [similar properties], but has only [N] publications.
     Observations with [instrument] would test whether
     [science question] by [measurement]."
    """
```

---

## Data Flow

```
User Input: "PDS 70"
       ↓
[Benchmark Profiler]
       ↓
Profile: T Tauri, K7, 113 pc, 5 Myr, transition disk, protoplanet
       ↓
[Analog Finder] ←── SIMBAD queries
       ↓
Candidates: 47 T Tauri stars in Sco-Cen
       ↓
[Study Depth Analyzer] ←── ADS queries
       ↓
Ranked by study depth:
  - PDS 70: 648 papers (benchmark)
  - PDS 66: 89 papers
  - RX J1615: 34 papers
  - DoAr 44: 12 papers  ← understudied!
  - ...
       ↓
[Proposal Ranker]
       ↓
Top candidates:
  1. DoAr 44 (12 papers, similar disk, observable)
  2. WSB 52 (8 papers, transition disk)
  3. ...
       ↓
[Proposal Generator]
       ↓
Output: Proposal-ready target list with justifications
```

---

## Implementation: proposal_targets.py

```python
#!/usr/bin/env python3
"""
Find understudied analogs to well-studied systems.
Generate proposal-ready target lists.
"""

import argparse
from astroquery.simbad import Simbad
import ads

def get_paper_count(object_name):
    """Get total paper count for an object from ADS."""
    query = f'title:"{object_name}" OR abstract:"{object_name}"'
    papers = ads.SearchQuery(q=query, rows=1)
    # Use the numFound from the query response
    return len(list(papers))

def find_similar_objects(benchmark, radius_deg=10, object_type='TT*'):
    """
    Find objects of similar type near benchmark.
    """
    # Get benchmark coordinates
    result = Simbad.query_object(benchmark)
    if result is None:
        return []

    ra = result[0]['ra']
    dec = result[0]['dec']

    # Query for similar objects
    custom_simbad = Simbad()
    custom_simbad.add_votable_fields('otype', 'sp_type', 'flux(V)')

    results = custom_simbad.query_region(
        f"{ra} {dec}",
        radius=f"{radius_deg}d"
    )

    # Filter by object type
    similar = []
    for row in results:
        if object_type in str(row['otype']):
            similar.append({
                'name': str(row['main_id']),
                'otype': str(row['otype']),
                'sp_type': str(row['sp_type']),
                'vmag': float(row['flux_V']) if row['flux_V'] else None
            })

    return similar

def rank_by_understudied(objects, min_papers=1, max_papers=50):
    """
    Rank objects by how understudied they are.
    """
    ranked = []
    for obj in objects:
        count = get_paper_count(obj['name'])
        if min_papers <= count <= max_papers:
            obj['paper_count'] = count
            ranked.append(obj)

    return sorted(ranked, key=lambda x: x['paper_count'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark', required=True,
                       help='Well-studied system to find analogs for')
    parser.add_argument('--radius', type=float, default=10,
                       help='Search radius in degrees')
    parser.add_argument('--max-papers', type=int, default=50,
                       help='Maximum papers for "understudied"')
    parser.add_argument('--output', help='Output file')

    args = parser.parse_args()

    # Find similar objects
    print(f"Finding objects similar to {args.benchmark}...")
    similar = find_similar_objects(args.benchmark, args.radius)

    # Rank by study depth
    print(f"Ranking {len(similar)} candidates by study depth...")
    understudied = rank_by_understudied(similar, max_papers=args.max_papers)

    # Output
    print(f"\n=== Understudied Analogs to {args.benchmark} ===\n")
    for i, obj in enumerate(understudied[:20], 1):
        print(f"{i}. {obj['name']}")
        print(f"   Type: {obj['otype']}, SpType: {obj['sp_type']}")
        print(f"   Papers: {obj['paper_count']}")
        if obj['vmag']:
            print(f"   V mag: {obj['vmag']:.1f}")
        print()

if __name__ == '__main__':
    main()
```

---

## Example Use Cases

### 1. Protoplanet Accretion Proposals

```bash
# Find understudied transition disks like PDS 70
python proposal_targets.py --benchmark "PDS 70" --radius 20

# Output:
# 1. DoAr 44 - 12 papers, similar disk structure
# 2. WSB 52 - 8 papers, gap detected
# 3. RNO 90 - 5 papers, accretion signature
```

### 2. HL Tau Analogs (Young Ringed Disks)

```bash
# Find young disks that might show similar rings
python proposal_targets.py --benchmark "HL Tau" --radius 10

# Focus on Class I/II sources in Taurus
```

### 3. TW Hya Analogs (Nearby Late-Stage Disks)

```bash
# Find nearby disks for detailed study
python proposal_targets.py --benchmark "TW Hya" --radius 30

# Output disks within 100 pc that are understudied
```

---

## Advanced Features (Future)

### 1. Property-Based Matching

Instead of just proximity, match on:
- Age (from association membership)
- Disk mass (from mm flux)
- Accretion rate (from literature)
- Disk substructure (from keywords)

### 2. Facility-Aware Ranking

Consider:
- Declination (ALMA vs VLT vs Keck)
- Brightness (exposure time feasibility)
- Prior JWST/ALMA observations
- Cycle timing

### 3. Science Case Generator

Auto-generate:
- Comparison science case
- Required observations
- Expected outcomes
- Time estimates

### 4. Proposal Abstract Writer

Using paper abstracts as training:
- Generate proposal-style text
- Cite relevant benchmark papers
- Formulate testable hypotheses

---

## Validation Approach

### Test: Rediscover Known Analogs

**Input**: PDS 70 as benchmark
**Expected**: Should surface systems like:
- PDS 66 (studied, but less than PDS 70)
- Transitional disks in same region

### Test: Find Genuine Gaps

**Input**: TW Hya as benchmark
**Check**: Are suggested targets actually observable?
Do they have disks? Are they genuinely understudied?

### Test: Proposal Quality

**Metric**: Would an astronomer actually propose these?
**Validation**: Review with domain expert

---

## Integration with Skill

### New SKILL.md section:

```markdown
### Proposal Target Generation

Find understudied analogs for observing proposals:

```bash
uv run scripts/proposal_targets.py \
    --benchmark "PDS 70" \
    --radius 20 \
    --max-papers 30 \
    --format proposal
```

This outputs proposal-ready target lists with:
- Object coordinates and properties
- Paper count comparison to benchmark
- Science justification template
```

---

## Summary

The proposal generation mode transforms the literature review skill from **retrospective analysis** to **prospective research planning**. It operationalizes the insight that well-studied systems reveal what's interesting, and similar but understudied systems are where new discoveries await.

**Key Innovation**: Using citation counts as a proxy for "study depth" to identify scientifically valuable but underexplored targets.
