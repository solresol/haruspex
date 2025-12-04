---
name: astro-literature
description: Search astronomical literature using ADS, analyze citation networks with recursive subagents, and determine scientific consensus. Use when analyzing research questions about astronomy topics.
---

# Astronomy Literature Review Skill

This skill enables comprehensive astronomical literature review by querying NASA ADS, SIMBAD, and NED databases. It uses a **recursive subagent architecture** where each paper is analyzed by a dedicated agent that can spawn additional agents to analyze important cited papers.

All analysis results are stored in a **SQLite database** for persistence and querying.

## When to Use This Skill

- Answering astronomy research questions by reviewing the literature
- Finding what the scientific consensus is on a topic
- Analyzing citation networks to understand how papers support or contradict each other
- Cross-referencing astronomical objects across databases
- Building a knowledge base of citation relationships

## Setup Requirements

### API Token
An ADS API token is required. The user should:
1. Create an account at https://ui.adsabs.harvard.edu/
2. Generate a token from Account Settings > API Token
3. Set the environment variable: `export ADS_DEV_KEY='your-token-here'`
   Or create the file: `~/.ads/dev_key` containing the token

### Python Dependencies
The skill uses `uv` for dependency management. From the skill directory:
```bash
cd .claude/skills/astro-literature
uv sync
```

Or run scripts directly (uv will auto-install dependencies):
```bash
uv run scripts/ads_search.py --help
```

### Database Location
The SQLite database is stored at: `~/.astro-literature/citations.db`

The database is created automatically on first use. You can view or modify it using the CLI tool:
```bash
uv run .claude/skills/astro-literature/scripts/litdb.py --help
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Agent (You)                         │
│  - Receives research question                               │
│  - Searches ADS for seed papers                             │
│  - Spawns Paper Analysis Subagents                          │
│  - Synthesizes final answer from database                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Paper Analysis Subagent                        │
│  - Given: bibcode/URL, research question, depth limit       │
│  - Fetches paper metadata and abstract from ADS             │
│  - Analyzes each citation in context                        │
│  - Classifies citation relationship                         │
│  - Stores results in SQLite database                        │
│  - May spawn sub-subagents for important cited papers       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   SQLite Database                           │
│  ~/.astro-literature/citations.db                           │
│  - papers: metadata cache                                   │
│  - citations: classified relationships                      │
│  - research_sessions: query history                         │
└─────────────────────────────────────────────────────────────┘
```

## Database Schema

The database has these tables:

### papers
Stores paper metadata fetched from ADS.
- `bibcode` (PRIMARY KEY): ADS bibcode
- `title`, `authors` (JSON), `year`, `publication`, `abstract`
- `doi`, `ads_url`, `citation_count`
- `fetched_at`: When the paper was fetched

### citations
Stores analyzed citation relationships.
- `citing_bibcode`, `cited_bibcode`: The citation edge
- `classification`: SUPPORTING, CONTRASTING, CONTEXTUAL, METHODOLOGICAL, NEUTRAL
- `confidence`: 0.0-1.0 confidence score
- `context_text`: The text where the citation appears (if available)
- `reasoning`: Why this classification was chosen
- `analyzed_at`: When the analysis was done

### research_sessions
Tracks research queries for continuity.
- `question`: The research question asked
- `started_at`, `completed_at`: Timestamps
- `summary`: Final synthesized answer
- `consensus_score`: -1.0 (disagreement) to +1.0 (strong consensus)

## Workflow

### Step 1: Parse the Research Question
Extract key concepts:
- Main topic/phenomenon
- Specific objects (if any)
- Time constraints
- Any specific authors or papers mentioned

### Step 2: Create Research Session
```bash
uv run .claude/skills/astro-literature/scripts/litdb.py session create \
    --question "What is the current understanding of dark matter halos?"
```

### Step 3: Search ADS for Seed Papers
```bash
uv run .claude/skills/astro-literature/scripts/ads_search.py \
    --query 'abstract:"dark matter halo" year:2020-2024 property:refereed' \
    --rows 20 --format json
```

### Step 4: Spawn Paper Analysis Subagents

For each important seed paper, spawn a subagent using the **Task tool**:

```
Use the Task tool with these parameters:
- subagent_type: "general-purpose"
- prompt: See the subagent prompt template below
```

**Subagent Prompt Template:**
```
You are analyzing a scientific paper for a literature review.

RESEARCH QUESTION: [The user's question]
PAPER TO ANALYZE: [bibcode or ADS URL]
DEPTH LIMIT: [How many levels deep to go, e.g., 2]
CURRENT DEPTH: [Current recursion depth, e.g., 0]

Instructions:
1. Read the subagent instructions at:
   .claude/skills/astro-literature/subagent-instructions.md

2. Follow those instructions to:
   - Fetch paper metadata using ads_search.py
   - Store paper in database using litdb.py
   - Analyze citations and classify each one
   - Store citation classifications in database
   - If CURRENT_DEPTH < DEPTH_LIMIT, spawn sub-subagents for
     papers that appear highly relevant to the research question

3. Return a summary of:
   - Paper title and key findings
   - Number of citations analyzed
   - Classification breakdown (supporting/contrasting/etc.)
   - Any papers you spawned subagents for
```

### Step 5: Query the Database for Results

After subagents complete, query the accumulated knowledge:

```bash
# View all citations for a paper
uv run .claude/skills/astro-literature/scripts/litdb.py citations list \
    --bibcode "2023ApJ...XXX...XX"

# Get classification summary
uv run .claude/skills/astro-literature/scripts/litdb.py citations summary \
    --bibcode "2023ApJ...XXX...XX"

# Find contrasting citations
uv run .claude/skills/astro-literature/scripts/litdb.py citations list \
    --classification CONTRASTING

# Export for analysis
uv run .claude/skills/astro-literature/scripts/litdb.py export \
    --session-id 1 --format json
```

### Step 6: Synthesize Findings

Query the database and produce a structured answer:

```markdown
## Research Question: [User's question]

### Summary
[2-3 sentence answer based on citation analysis]

### Database Statistics
- Papers analyzed: N (from `litdb.py papers count`)
- Citations classified: M (from `litdb.py citations count`)
- Analysis depth: D levels

### Current State of the Art
[Based on supporting citations from recent papers]

### Key Papers
1. [Author et al. Year] - [Brief description] (N citations)
   - Supporting citations: X
   - Contrasting citations: Y

### Scientific Consensus
[Based on consensus_score and classification breakdown]

### Areas of Active Debate
[Papers with high contrasting citation counts]

### Recommended Reading
[Top papers by relevance and citation impact]
```

## CLI Tool Reference

The `litdb.py` script manages the SQLite database. Run from the skill directory or use full paths:

```bash
# From the skill directory (.claude/skills/astro-literature):
uv run scripts/litdb.py <command>

# Or with full path from anywhere:
uv run .claude/skills/astro-literature/scripts/litdb.py <command>
```

### Paper Commands
```bash
uv run scripts/litdb.py papers add --bibcode "..." --title "..." [--json '{...}']
uv run scripts/litdb.py papers get --bibcode "..."
uv run scripts/litdb.py papers list [--year 2023] [--limit 20]
uv run scripts/litdb.py papers count
```

### Citation Commands
```bash
uv run scripts/litdb.py citations add --citing "..." --cited "..." \
    --classification SUPPORTING [--confidence 0.8] [--context "..."]
uv run scripts/litdb.py citations list [--bibcode "..."] [--classification CONTRASTING]
uv run scripts/litdb.py citations summary [--bibcode "..."]
uv run scripts/litdb.py citations count
```

### Session Commands
```bash
uv run scripts/litdb.py session create --question "..."
uv run scripts/litdb.py session list
uv run scripts/litdb.py session complete --id 1 --summary "..." [--consensus-score 0.5]
```

### Export/Stats
```bash
uv run scripts/litdb.py export [--session-id 1] [--format json|csv]
uv run scripts/litdb.py stats
```

## Citation Classifications

When analyzing citations, classify each as:

| Classification | Description | Example Signals |
|---------------|-------------|-----------------|
| **SUPPORTING** | Agrees with, builds upon, confirms | "consistent with", "confirms", "as shown by" |
| **CONTRASTING** | Disagrees, challenges, presents alternatives | "however", "in contrast", "unlike", "tension with" |
| **CONTEXTUAL** | Background, history, general facts | "discovered by", "first proposed", "review" |
| **METHODOLOGICAL** | References methods, data, tools | "using the method of", "data from", "code from" |
| **NEUTRAL** | Simple acknowledgment, no clear stance | No strong indicators |

## Important Notes

- **Depth Limiting**: Always set a depth limit (2-3) to prevent runaway recursion
- **Rate Limiting**: ADS has query limits; space out requests
- **Database Persistence**: Results accumulate across sessions
- **Incremental Analysis**: Check database before re-analyzing papers
- Prefer refereed publications for consensus views
- High citation count doesn't always mean high quality
- Be explicit about limitations and uncertainties
