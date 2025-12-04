---
name: astro-literature
description: Search astronomical literature using ADS, analyze citation networks, and determine scientific consensus. Use when analyzing research questions about astronomy topics.
---

# Astronomy Literature Review Skill

This skill enables comprehensive astronomical literature review by querying NASA ADS, SIMBAD, and NED databases to answer research questions and determine the state of the art on any astronomy topic.

## When to Use This Skill

- Answering astronomy research questions by reviewing the literature
- Finding what the scientific consensus is on a topic
- Analyzing citation networks to understand how papers support or contradict each other
- Cross-referencing astronomical objects across databases
- Identifying key papers and their influence on a field

## Setup Requirements

### API Token
An ADS API token is required. The user should:
1. Create an account at https://ui.adsabs.harvard.edu/
2. Generate a token from Account Settings > API Token
3. Set the environment variable: `export ADS_DEV_KEY='your-token-here'`
   Or create the file: `~/.ads/dev_key` containing the token

### Python Dependencies
Install required packages:
```bash
pip install astroquery ads requests
```

## Workflow

When the user asks a research question about astronomy, follow this workflow:

### Step 1: Parse the Research Question
Extract key concepts from the question:
- Main topic/phenomenon
- Specific objects (if any)
- Time constraints (recent work vs historical)
- Any specific authors or papers mentioned

### Step 2: Search ADS for Relevant Papers
Use the `scripts/ads_search.py` script to find papers:

```bash
python .claude/skills/astro-literature/scripts/ads_search.py --query "your search query" --rows 50
```

Query syntax tips:
- Use quotes for exact phrases: `"dark energy"`
- Use `author:"name"` for author searches
- Use `title:keyword` or `abstract:keyword` for specific fields
- Use `year:2020-2024` for date ranges
- Use `citations(query)` to find papers citing matches
- Use `references(query)` to find papers cited by matches

### Step 3: Analyze Citation Network
For key papers found, analyze their citation relationships:

```bash
python .claude/skills/astro-literature/scripts/citation_analysis.py --bibcode "2023ApJ...XXX...XX"
```

This script:
- Retrieves papers that cite the target paper
- Retrieves papers referenced by the target paper
- Searches for context around citations (when available)
- Classifies citation types

### Step 4: Classify Citation Context
For each citation found, determine its type:
- **Supporting**: Citation explicitly agrees with or builds upon the cited work
- **Contrasting**: Citation disagrees with, challenges, or presents alternatives
- **Contextual**: Citation provides background, describes general facts
- **Methodological**: Citation references methods, data, or tools
- **Neutral**: Simple acknowledgment without stance

Use the `scripts/classify_citations.py` script to help classify:

```bash
python .claude/skills/astro-literature/scripts/classify_citations.py --input citations.json
```

### Step 5: Cross-Reference with SIMBAD/NED (Optional)
If the question involves specific astronomical objects:

```bash
python .claude/skills/astro-literature/scripts/object_lookup.py --object "M31" --database simbad
python .claude/skills/astro-literature/scripts/object_lookup.py --object "NGC 224" --database ned
```

### Step 6: Synthesize Findings
Produce a structured answer that includes:

1. **Summary**: One-paragraph answer to the research question
2. **State of the Art**: Current scientific consensus or major viewpoints
3. **Key Papers**: Most influential papers with brief descriptions
4. **Points of Agreement**: What most researchers accept
5. **Points of Debate**: Where there is active disagreement
6. **Citation Analysis**: Breakdown of supporting vs contrasting citations
7. **Recommended Reading**: 3-5 papers for deeper understanding

## Example Queries

### Simple Topic Query
User: "What is the current understanding of dark matter halos?"

1. Search: `abstract:"dark matter halo" year:2020-2024 property:refereed`
2. Identify top-cited papers
3. Analyze citation network for key paper
4. Report consensus and ongoing debates

### Object-Specific Query
User: "What do we know about the supermassive black hole in M87?"

1. Query SIMBAD for M87 identifiers
2. Search ADS: `object:M87 abstract:"black hole" year:2019-2024`
3. Include Event Horizon Telescope papers
4. Analyze how subsequent papers cite EHT results

### Methodology Debate Query
User: "Is there disagreement about how to measure the Hubble constant?"

1. Search: `title:"Hubble constant" OR title:"H0 tension"`
2. Find papers on different measurement methods
3. Specifically look for contrasting citations
4. Map the "tension" landscape

## Output Format

Present findings in this structure:

```markdown
## Research Question: [User's question]

### Summary
[2-3 sentence answer]

### Current State of the Art
[Overview of where the field stands]

### Key Papers
1. [Author et al. Year] - [Brief description] (N citations)
2. ...

### Scientific Consensus
- [Point of agreement 1]
- [Point of agreement 2]

### Areas of Active Debate
- [Debate topic 1]: [Side A] vs [Side B]
- [Debate topic 2]: ...

### Citation Analysis
- Papers examined: N
- Supporting citations: X%
- Contrasting citations: Y%
- Contextual citations: Z%

### Recommended Reading
1. [Paper 1] - [Why it's recommended]
2. ...
```

## Important Notes

- Always check paper publication dates for recency
- Prefer refereed publications over preprints for consensus views
- High citation count doesn't always mean high quality
- Look for review papers to get field overviews
- Be explicit about limitations and uncertainties
- Distinguish between observational consensus and theoretical consensus
