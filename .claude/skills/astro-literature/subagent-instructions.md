# Paper Analysis Subagent Instructions

You are a subagent tasked with analyzing a scientific paper for a literature review. Your job is to:
1. Fetch and store paper metadata
2. Analyze how this paper cites other papers
3. Classify each citation relationship
4. Store results in the database
5. Optionally spawn sub-subagents for important papers

## Input Parameters

You should receive these parameters from the parent agent:
- **RESEARCH_QUESTION**: The question being investigated
- **PAPER_ID**: Bibcode, DOI, or ADS URL of the paper to analyze
- **DEPTH_LIMIT**: Maximum recursion depth (typically 2-3)
- **CURRENT_DEPTH**: Your current depth in the recursion (starts at 0)
- **SESSION_ID**: The research session ID (optional)

## Setup

The skill is located at: `.claude/skills/astro-literature/`

Scripts directory: `.claude/skills/astro-literature/scripts/`

Database location: `~/.astro-literature/citations.db`

## Workflow

### Step 1: Extract Bibcode

If given a URL like `https://ui.adsabs.harvard.edu/abs/2019ApJ...882L...2S/abstract`, extract the bibcode: `2019ApJ...882L...2S`

If given a DOI, search ADS:
```bash
uv run .claude/skills/astro-literature/scripts/ads_search.py \
    --query 'doi:"10.xxxx/xxxxx"' --format json
```

### Step 2: Check if Already Analyzed

Before fetching, check if this paper is already in the database:
```bash
uv run .claude/skills/astro-literature/scripts/litdb.py papers get --bibcode "BIBCODE"
```

If it exists and has recent analysis, you can skip to Step 5 (spawning subagents).

### Step 3: Fetch Paper Metadata

Get full paper details from ADS:
```bash
uv run .claude/skills/astro-literature/scripts/ads_search.py \
    --query 'bibcode:BIBCODE' --format json --output /tmp/paper.json
```

Store the paper in the database:
```bash
uv run .claude/skills/astro-literature/scripts/litdb.py papers add \
    --json "$(cat /tmp/paper.json | jq '.[0]')"
```

If you have a SESSION_ID, add the paper to the session:
```bash
uv run .claude/skills/astro-literature/scripts/litdb.py session add-paper \
    --session-id SESSION_ID --bibcode "BIBCODE" --depth CURRENT_DEPTH
```

### Step 4: Analyze Citations

Get papers that this paper cites (references):
```bash
uv run .claude/skills/astro-literature/scripts/ads_search.py \
    --references "BIBCODE" --rows 50 --format json --output /tmp/refs.json
```

Get papers that cite this paper:
```bash
uv run .claude/skills/astro-literature/scripts/ads_search.py \
    --citations "BIBCODE" --rows 50 --format json --output /tmp/cites.json
```

### Step 5: Classify Each Citation

For each paper that cites this paper, classify the relationship.

**Read the abstract of the citing paper** and determine how it relates to the paper you're analyzing. Consider:

1. **SUPPORTING**: Does the citing paper:
   - Confirm findings?
   - Build upon the work?
   - Use it as validation?
   - Express agreement?

   Look for: "consistent with", "confirms", "as shown by", "in agreement with"

2. **CONTRASTING**: Does the citing paper:
   - Challenge the findings?
   - Present alternative conclusions?
   - Report contradictory results?
   - Question the methodology?

   Look for: "however", "in contrast", "unlike", "does not support", "tension with"

3. **REFUTING**: Does the citing paper definitively rule out the cited work's hypothesis?
   - Provide strong statistical evidence against it (>5σ)?
   - Show the hypothesis is incompatible with observations?
   - Demonstrate the idea has been abandoned by the field?

   Look for: "ruled out", "excluded", "disproven", "refuted", "inconsistent at Nσ",
   "no longer viable", "conclusively shown to be incorrect"

   ⚠️ **REFUTING is stronger than CONTRASTING** - only use when evidence is definitive.
   If a hypothesis is refuted, also create a hypothesis entry (see Step 6b).

4. **CONTEXTUAL**: Does the citing paper:
   - Use it for background?
   - Mention it historically?
   - Reference it for context?

   Look for: "first discovered by", "pioneering work", "established that"

5. **METHODOLOGICAL**: Does the citing paper:
   - Use methods from this paper?
   - Reference software/code?
   - Use datasets from this paper?

   Look for: "using the method of", "following", "adopting the approach"

6. **NEUTRAL**: No clear stance, simple acknowledgment

### Step 6: Store Classifications

For each citation relationship you analyze:
```bash
uv run .claude/skills/astro-literature/scripts/litdb.py citations add \
    --citing "CITING_BIBCODE" \
    --cited "THIS_PAPER_BIBCODE" \
    --classification CLASSIFICATION \
    --confidence 0.8 \
    --context "The relevant sentence from the abstract" \
    --reasoning "Brief explanation of why this classification" \
    --agent "subagent-depth-N"
```

### Step 6b: Track Ruled-Out Hypotheses

When you classify a citation as **REFUTING**, you should also record the hypothesis that was ruled out:

```bash
# Add the hypothesis
uv run .claude/skills/astro-literature/scripts/litdb.py hypothesis add \
    --name "Brief name of the hypothesis" \
    --description "What the hypothesis claimed" \
    --status RULED_OUT \
    --origin "ORIGINAL_PAPER_BIBCODE" \
    --ruling "REFUTING_PAPER_BIBCODE" \
    --reason "Why it was ruled out (brief)"

# Link the refuting paper
uv run .claude/skills/astro-literature/scripts/litdb.py hypothesis link \
    --hypothesis-id N --bibcode "REFUTING_BIBCODE" --stance REFUTES
```

**Examples of ruled-out hypotheses to look for:**
- Models that predicted something observations don't show
- Mechanisms that were proposed but later shown to be insufficient
- Parameter values that are now excluded by data
- Theories that were superseded by better explanations

This is crucial for answering "what is the state of the art" - knowing what ideas are **no longer in play** is as important as knowing what ideas are current.

### Step 7: Spawn Sub-Subagents (if depth allows)

If CURRENT_DEPTH < DEPTH_LIMIT, consider spawning subagents for papers that:
- Are highly relevant to the RESEARCH_QUESTION
- Have high citation counts
- Present contrasting views (important for understanding debate)
- Are recent and may represent current state of the art

To spawn a subagent, use the Task tool with:
```
subagent_type: "general-purpose"
prompt: |
  You are analyzing a scientific paper for a literature review.

  RESEARCH_QUESTION: [same question]
  PAPER_ID: [bibcode of the paper to analyze]
  DEPTH_LIMIT: [same limit]
  CURRENT_DEPTH: [CURRENT_DEPTH + 1]
  SESSION_ID: [same session]

  Instructions:
  1. Read the subagent instructions at:
     .claude/skills/astro-literature/subagent-instructions.md

  2. Follow those instructions completely.

  3. Return a summary of your analysis.
```

**Important**: Limit the number of subagents you spawn (5-10 per paper) to avoid explosion.

### Step 8: Return Summary

After completing your analysis, return a summary to the parent agent:

```
## Paper Analysis Summary

**Paper**: [Title] (BIBCODE)
**Year**: XXXX
**Citations**: N

### Relevance to Research Question
[How this paper relates to the question]

### Key Findings
[Main conclusions of the paper]

### Citation Analysis
- Total citations analyzed: N
- SUPPORTING: X
- CONTRASTING: Y
- REFUTING: R ⚠️
- CONTEXTUAL: Z
- METHODOLOGICAL: W
- NEUTRAL: V

### Ruled-Out Hypotheses Found ⚠️
[List any hypotheses that have been definitively ruled out, with:
- Hypothesis name
- Why it was ruled out
- Which paper ruled it out]

### Notable Contrasting Citations
[List any papers that disagree - these are important for understanding debate]

### Subagents Spawned
[List any subagents you spawned and for which papers]

### Database Status
Papers stored: N
Citations classified: M
```

## Important Notes

1. **Rate Limiting**: Don't make too many ADS queries in quick succession
2. **Deduplication**: Always check the database before re-analyzing
3. **Depth Limits**: Respect the DEPTH_LIMIT to prevent infinite recursion
4. **Relevance Filtering**: Only spawn subagents for truly relevant papers
5. **Error Handling**: If a paper isn't found in ADS, note it and continue
6. **Context Preservation**: Store enough context in the database for later synthesis

## Example Classification

Paper: "The Hubble Tension" (2021ApJ...XXX...YY)
Citing paper abstract: "Our results using the tip of the red giant branch method yield H0 = 69.8 km/s/Mpc, which is in tension with the value of 73.0 reported by Riess et al. (2021)..."

Classification:
- **CONTRASTING** (confidence: 0.85)
- Context: "in tension with the value of 73.0 reported by Riess et al."
- Reasoning: "Explicit mention of tension with differing measurement value"
