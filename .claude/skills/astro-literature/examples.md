# Example Queries and Workflows

This document provides example queries and workflows for the astro-literature skill.

## Example 1: Topic Survey - Dark Matter Halos

**Question:** What is the current understanding of dark matter halo profiles?

### Step 1: Initial Search
```bash
python scripts/ads_search.py --query 'title:"dark matter halo" abstract:profile' \
    --year-start 2020 --refereed --rows 30 --format summary
```

### Step 2: Identify Key Papers
Look for papers with high citation counts. For example, the NFW profile paper:
```bash
python scripts/ads_search.py --query 'author:"Navarro" title:"universal density profile"' \
    --format json --output nfw.json
```

### Step 3: Citation Analysis
```bash
python scripts/citation_analysis.py --bibcode 1997ApJ...490..493N \
    --citing-limit 100 --format json --output nfw_network.json
```

### Step 4: Classification
```bash
python scripts/classify_citations.py --input nfw_network.json --format summary
```

---

## Example 2: Object-Specific Query - M87 Black Hole

**Question:** What do recent papers say about the supermassive black hole in M87?

### Step 1: Get Object Info
```bash
python scripts/object_lookup.py --object "M87" --cross-match
```

### Step 2: Search ADS
```bash
python scripts/ads_search.py --query 'object:M87 abstract:"black hole" year:2019-2024' \
    --refereed --rows 50
```

### Step 3: Focus on EHT Results
```bash
# The famous first image paper
python scripts/citation_analysis.py --bibcode 2019ApJ...875L...1E \
    --citing-limit 100 --format json --output eht_m87.json
```

### Step 4: Analyze Reception
```bash
python scripts/classify_citations.py --input eht_m87.json
```

---

## Example 3: Methodological Debate - Hubble Tension

**Question:** What is the status of the Hubble constant tension?

### Step 1: Search for Key Papers
```bash
# Riess et al. (local distance ladder)
python scripts/ads_search.py --query 'author:"Riess" title:"Hubble" year:2020-2024' \
    --refereed --rows 20

# Planck Collaboration (CMB-based)
python scripts/ads_search.py --query 'author:"Planck Collaboration" title:"cosmological parameters"' \
    --year-start 2018 --refereed --rows 10
```

### Step 2: Find Papers Discussing Both
```bash
python scripts/ads_search.py \
    --query 'abstract:"Hubble tension" OR abstract:"H0 tension"' \
    --year-start 2020 --refereed --rows 50
```

### Step 3: Analyze a Key Tension Paper
```bash
python scripts/citation_analysis.py --bibcode 2019NatAs...3..891V \
    --format json --output tension.json
python scripts/classify_citations.py --input tension.json
```

---

## Example 4: Finding Review Papers

**Question:** What are the best review papers on exoplanet atmospheres?

### Step 1: Search for Reviews
```bash
python scripts/ads_search.py \
    --query 'title:review abstract:"exoplanet atmosphere"' \
    --refereed --sort 'citation_count desc' --rows 20
```

### Step 2: Find Most-Cited Recent Work
```bash
python scripts/ads_search.py \
    --query 'abstract:"exoplanet atmosphere" property:refereed' \
    --year-start 2020 --sort 'citation_count desc' --rows 30
```

---

## Example 5: Author Impact Analysis

**Question:** What is the influence of a specific researcher's work?

### Step 1: Find Their Papers
```bash
python scripts/ads_search.py --query 'author:"^Sagan, Carl"' \
    --sort 'citation_count desc' --rows 20
```

### Step 2: Analyze Most-Cited Work
```bash
# Pale Blue Dot perspective
python scripts/citation_analysis.py --bibcode 1994pal..book.....S \
    --citing-limit 50
```

---

## ADS Query Syntax Tips

### Field Searches
- `title:"exact phrase"` - Search in title
- `abstract:keyword` - Search in abstract
- `author:"Last, First"` - Search by author
- `author:"^Last"` - First author only
- `year:2020-2024` - Date range
- `bibcode:2019ApJ...` - Specific paper

### Boolean Operators
- `AND` (default between terms)
- `OR` - Either term
- `NOT` - Exclude term
- Parentheses for grouping

### Special Filters
- `property:refereed` - Peer-reviewed only
- `property:article` - Journal articles
- `doctype:review` - Review papers
- `data:NED` - Papers with NED data
- `data:SIMBAD` - Papers with SIMBAD data

### Citation Operators
- `citations(query)` - Papers citing the results
- `references(query)` - Papers referenced by results
- `trending(query)` - Currently trending papers
- `useful(query)` - Frequently co-cited papers
