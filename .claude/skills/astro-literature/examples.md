# Example Queries and Workflows

This document provides example queries and workflows for the astro-literature skill using the subagent architecture and SQLite database.

## Quick Reference

All scripts are run with `uv run` from the skill directory:
```bash
cd .claude/skills/astro-literature
uv run scripts/ads_search.py --help
uv run scripts/litdb.py --help
```

Database location: `~/.astro-literature/citations.db`

---

## Example 1: Full Literature Review with Subagents

**Question:** What is the current understanding of dark matter halo profiles?

### Step 1: Create a Research Session
```bash
uv run scripts/litdb.py session create \
    --question "What is the current understanding of dark matter halo profiles?"
```
Output: `Created session 1: What is the current understanding...`

### Step 2: Search for Seed Papers
```bash
uv run scripts/ads_search.py \
    --query 'title:"dark matter halo" abstract:profile year:2020-2024 property:refereed' \
    --rows 20 --format summary
```

### Step 3: Spawn Subagent for Key Paper

Use the Task tool with subagent_type="general-purpose":
```
You are analyzing a scientific paper for a literature review.

RESEARCH_QUESTION: What is the current understanding of dark matter halo profiles?
PAPER_ID: 1997ApJ...490..493N
DEPTH_LIMIT: 2
CURRENT_DEPTH: 0
SESSION_ID: 1

Instructions:
1. Read the subagent instructions at:
   .claude/skills/astro-literature/subagent-instructions.md
2. Follow those instructions completely.
3. Return a summary of your analysis.
```

### Step 4: Query Database for Results
```bash
# Check how many papers were analyzed
uv run scripts/litdb.py papers count

# View citation breakdown for the NFW paper
uv run scripts/litdb.py citations summary --bibcode 1997ApJ...490..493N

# Find contrasting citations (important for debate)
uv run scripts/litdb.py citations list --classification CONTRASTING

# Overall database stats
uv run scripts/litdb.py stats
```

### Step 5: Export and Complete Session
```bash
# Export all data for this session
uv run scripts/litdb.py export --session-id 1 --format json --output session1.json

# Mark session complete with summary
uv run scripts/litdb.py session complete --id 1 \
    --summary "NFW profile remains foundational; alternatives include Einasto profile..." \
    --consensus-score 0.6
```

---

## Example 2: Hubble Tension Investigation

**Question:** What is the current status of the Hubble tension?

### Step 1: Create Session and Find Seed Papers
```bash
uv run scripts/litdb.py session create \
    --question "What is the current status of the Hubble tension?"

# Find key tension papers
uv run scripts/ads_search.py \
    --query 'abstract:"Hubble tension" OR abstract:"H0 tension" year:2020-2024' \
    --refereed --rows 30 --format json
```

### Step 2: Spawn Parallel Subagents

Launch multiple subagents in parallel for different perspectives:

**Subagent 1: Distance Ladder (Riess)**
```
PAPER_ID: 2022ApJ...934L...7R  (example Riess paper)
RESEARCH_QUESTION: What is the current status of the Hubble tension?
DEPTH_LIMIT: 2
CURRENT_DEPTH: 0
```

**Subagent 2: CMB-based (Planck)**
```
PAPER_ID: 2020A&A...641A...6P  (Planck 2018)
RESEARCH_QUESTION: What is the current status of the Hubble tension?
DEPTH_LIMIT: 2
CURRENT_DEPTH: 0
```

### Step 3: Analyze the Debate
```bash
# See all contrasting citations
uv run scripts/litdb.py citations list --classification CONTRASTING --verbose

# Get overall consensus score
uv run scripts/litdb.py citations summary
```

---

## Example 3: Object-Specific Query with SIMBAD/NED

**Question:** What do we know about the supermassive black hole in M87?

### Step 1: Cross-Reference Object
```bash
uv run scripts/object_lookup.py --object "M87" --cross-match
```

### Step 2: Search with Object Name
```bash
uv run scripts/ads_search.py \
    --query 'object:M87 abstract:"black hole" year:2019-2024' \
    --refereed --rows 30 --format json
```

### Step 3: Focus on EHT Paper

Spawn subagent for the famous first image paper:
```
PAPER_ID: 2019ApJ...875L...1E
RESEARCH_QUESTION: What do we know about the supermassive black hole in M87?
DEPTH_LIMIT: 2
CURRENT_DEPTH: 0
```

### Step 4: Query Results
```bash
# How has the EHT paper been received?
uv run scripts/litdb.py citations summary --bibcode 2019ApJ...875L...1E

# Any challenges to the results?
uv run scripts/litdb.py citations list \
    --cited 2019ApJ...875L...1E \
    --classification CONTRASTING
```

---

## Example 4: Quick Single-Paper Analysis

For a quick analysis without a full session:

```bash
# Fetch and store paper
uv run scripts/ads_search.py --query 'bibcode:2016PhRvL.116f1102A' --format json | \
    uv run scripts/litdb.py papers add --json "$(cat -)"

# Get citation network
uv run scripts/citation_analysis.py --bibcode 2016PhRvL.116f1102A \
    --format json --output /tmp/gw150914.json

# Classify citations
uv run scripts/classify_citations.py --input /tmp/gw150914.json --format summary
```

---

## Database CLI Reference

### Papers
```bash
# Add a paper (with JSON data)
uv run scripts/litdb.py papers add --json '{"bibcode":"...", "title":"...", ...}'

# Get paper details
uv run scripts/litdb.py papers get --bibcode "2019ApJ...882L...2S"

# List papers by year
uv run scripts/litdb.py papers list --year 2023 --limit 10

# Count total papers
uv run scripts/litdb.py papers count
```

### Citations
```bash
# Add a citation classification
uv run scripts/litdb.py citations add \
    --citing "2023ApJ...XXX...YY" \
    --cited "2019ApJ...882L...2S" \
    --classification SUPPORTING \
    --confidence 0.85 \
    --context "Our results confirm the findings of..." \
    --reasoning "Explicit confirmation language"

# List citations for a paper
uv run scripts/litdb.py citations list --bibcode "2019ApJ...882L...2S"

# Filter by classification
uv run scripts/litdb.py citations list --classification CONTRASTING --verbose

# Get summary statistics
uv run scripts/litdb.py citations summary --bibcode "2019ApJ...882L...2S"
```

### Sessions
```bash
# Create session
uv run scripts/litdb.py session create --question "Your question here"

# List sessions
uv run scripts/litdb.py session list

# Add paper to session
uv run scripts/litdb.py session add-paper \
    --session-id 1 \
    --bibcode "2023ApJ...XXX...YY" \
    --depth 0 \
    --seed

# Complete session
uv run scripts/litdb.py session complete \
    --id 1 \
    --summary "Summary of findings..." \
    --consensus-score 0.5
```

### Export and Stats
```bash
# Export session data
uv run scripts/litdb.py export --session-id 1 --format json --output session.json

# Export all as CSV
uv run scripts/litdb.py export --format csv --output citations.csv

# Show database statistics
uv run scripts/litdb.py stats

# Reset database (careful!)
uv run scripts/litdb.py reset --confirm
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
- `object:M87` - Papers about object

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

---

## Tips for Effective Analysis

1. **Start with review papers** to get overview before diving deep
2. **Use DEPTH_LIMIT=2** for most analyses; 3 only for narrow questions
3. **Prioritize contrasting citations** - they reveal the debate
4. **Check high citation papers** - they're usually influential
5. **Verify recent papers** - the field may have evolved
6. **Cross-check with SIMBAD/NED** for object-specific queries
7. **Export sessions** before starting new ones for continuity
