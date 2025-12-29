# Create a Medical Literature Analysis System Based on Haruspex

I want to create a new project called **medicus** (or similar name) that is functionally equivalent to the **haruspex** astronomy literature analysis system, but adapted for medical and clinical research.

## Reference Architecture

Use the existing `/home/user/haruspex` project as your architectural template. Study these key components:

1. **Overall structure**: `.claude/skills/astro-literature/` directory organization
2. **Database schema**: `scripts/litdb.py` - the SQLite database design
3. **Subagent architecture**: `subagent-instructions.md` - how recursive agents work
4. **Classification system**: `classify_citations.py` - the 6-type citation classification
5. **Hypothesis tracking**: The REFUTING classification and hypothesis table
6. **Dependencies**: `pyproject.toml` using `uv` for Python execution

## What I Want You To Build

Create a complete medical literature analysis system with:

### 1. Project Setup

- **Location**: Create a new directory called `medicus` (outside of haruspex)
- **Structure**: `.claude/skills/med-literature/` as the main skill directory
- **Python management**: Use `uv` (not pip) for all dependencies
- **Database location**: `~/.med-literature/citations.db`

### 2. Medical Literature APIs to Integrate

Replace NASA ADS with medical databases:

**Primary API - PubMed/NCBI**:
- Use the `biopython` package (Bio.Entrez) to access PubMed
- Search: `Entrez.esearch(db='pubmed', term=query)`
- Fetch: `Entrez.efetch(db='pubmed', id=pmid, retmode='xml')`
- Citations: `Entrez.elink(dbfrom='pubmed', id=pmid, linkname='pubmed_pubmed_citedin')`

**Secondary APIs** (if time permits):
- ClinicalTrials.gov REST API for trial registry data
- CrossRef API for DOI resolution and reference extraction

**Key fields to extract**:
- PMID (PubMed ID) - equivalent to bibcode
- Title, authors (list), journal, year, volume, pages
- Abstract text
- MeSH terms (Medical Subject Headings) - equivalent to keywords
- Publication types (Clinical Trial, Review, Meta-Analysis, etc.)
- DOI, PubMed Central ID (PMCID)

### 3. Database Schema Adaptations

Start with the haruspex schema but make these medical-specific changes:

**papers table** - Add these fields:
- `pmid` (TEXT PRIMARY KEY) - instead of bibcode
- `pmcid` (TEXT) - PubMed Central ID
- `publication_types` (JSON) - e.g., ["Clinical Trial", "Randomized Controlled Trial"]
- `mesh_terms` (JSON) - Medical Subject Headings for indexing
- `patient_population` (TEXT) - If extractable from abstract (e.g., "adults", "pediatric")
- `study_design` (TEXT) - RCT, observational, case report, review, etc.

**citations table** - Modify classifications:
Keep the structure but update classification types (see section 4 below)

**hypotheses table** - Adapt for medical context:
- Track treatment efficacy claims
- Disease mechanism theories
- Drug safety concerns
- Clinical practice guidelines

Add these medical-specific tables:

**clinical_trials table**:
- `nct_id` (TEXT PRIMARY KEY) - ClinicalTrials.gov ID
- `title`, `status`, `phase`, `enrollment`
- `conditions` (JSON), `interventions` (JSON)
- `primary_outcome`, `results_available`
- `linked_pmid` (FK to papers)

**outcomes table** (for tracking clinical endpoints):
- `paper_pmid` (FK to papers)
- `outcome_type` (TEXT) - mortality, morbidity, quality_of_life, surrogate
- `outcome_measure` (TEXT)
- `result_summary` (TEXT)
- `statistical_significance` (REAL) - p-value

### 4. Medical Citation Classifications

Replace the 6 astronomy classification types with medical research context:

| Type | When to Use | Pattern Examples |
|------|-------------|------------------|
| **SUPPORTING** | Confirms efficacy, safety, mechanism | "demonstrated efficacy", "confirmed safety", "consistent with", "validates" |
| **CONTRASTING** | Alternative interpretations, conflicting data | "however", "in contrast", "conflicting results", "inconsistent with" |
| **REFUTING** | Rules out efficacy/safety, contradicts definitively | "failed to demonstrate", "no significant difference", "ruled out", "contraindicated", "inferior to" |
| **METHODOLOGICAL** | Cites methods, protocols, statistical tools | "using method of", "protocol described in", "statistical approach from" |
| **CONTEXTUAL** | Background, epidemiology, history | "first described by", "traditionally", "pioneered by" |
| **META_ANALYSIS** | Systematic reviews citing primary studies | "meta-analysis of", "systematic review including", "pooled analysis" |

**Key differences from astronomy**:
- `META_ANALYSIS` is new and should be weighted highly in consensus
- `REFUTING` in medicine often means "failed to show benefit" or "non-inferiority"
- Study design should influence confidence scores (RCT > observational > case report)

### 5. Consensus Scoring for Medicine

Adapt the consensus calculation to weight by study quality:

**Study quality weights**:
- Meta-analysis / Systematic review: 3.0x weight
- Randomized Controlled Trial (RCT): 2.0x weight
- Observational study: 1.0x weight
- Case series / case report: 0.5x weight

**Consensus formula**:
```
score = (weighted_SUPPORTING + weighted_META_ANALYSIS - weighted_CONTRASTING - 2×weighted_REFUTING)
        / (total_weighted_papers)
```

### 6. Scripts to Create

Model after haruspex but adapt for medical domain:

**pubmed_search.py**:
- Search PubMed with flexible query syntax
- Support MeSH term searches
- Filter by publication type, date range, journal impact
- Return PMID, title, authors, abstract, MeSH terms, publication types
- Commands: `--query`, `--citations PMID`, `--references PMID`, `--format json|summary|pmids`

**citation_analysis.py**:
- Extract citation network for a given PMID
- Get citing papers (papers that reference this one)
- Get referenced papers (papers this one cites)
- Return structured JSON

**classify_citations.py**:
- Pattern-based classification using medical terminology
- Build regex patterns for each of the 6 medical classification types
- Include study design detection (RCT, observational, etc.)
- Return: (classification, confidence, study_weight, matched_patterns)
- Aggregate function for consensus scoring

**litdb.py** - Medical Database CLI:
Adapt all the haruspex commands but for medical schema:

```bash
# Papers
litdb.py papers add --pmid "12345678" --title "..." --study-design "RCT"
litdb.py papers get --pmid "..."
litdb.py papers list [--year 2020] [--study-design RCT] [--limit 20]

# Citations
litdb.py citations add --citing "..." --cited "..." --classification SUPPORTING --study-weight 2.0
litdb.py citations summary [--pmid "..."]  # Should show weighted consensus

# Sessions
litdb.py session create --question "Is metformin effective for type 2 diabetes?"
litdb.py session add-paper --session-id 1 --pmid "..." --depth 0 --seed
litdb.py session complete --id 1 --summary "..." --consensus-score 0.75

# Hypotheses (medical context)
litdb.py hypothesis add --name "Drug X reduces mortality" --status RULED_OUT --ruling "PMID:12345"
litdb.py hypothesis ruled-out  # Show disproven treatments/theories

# Outcomes
litdb.py outcome add --pmid "..." --type mortality --measure "all-cause mortality" --result "HR 0.85, p=0.03"
litdb.py outcome list --pmid "..."

# Export
litdb.py export [--format json|csv]
litdb.py stats
```

**trial_lookup.py** (NEW - medical specific):
- Query ClinicalTrials.gov API for trial details
- Cross-reference NCT IDs with PubMed publications
- Commands: `--nct-id NCT12345678`, `--condition "diabetes"`, `--intervention "metformin"`

### 7. Subagent Architecture

Create `subagent-instructions.md` that mirrors haruspex but for medical papers:

**Subagent workflow**:
1. Extract PMID from user input (PMID, DOI, or PubMed URL)
2. Check database - skip if already analyzed at this depth
3. Fetch paper metadata from PubMed (title, abstract, authors, MeSH terms, publication types)
4. Identify study design (RCT, observational, review, etc.)
5. Get citing papers using PubMed's citation API
6. For each citing paper:
   - Fetch its abstract
   - Classify the citation relationship (SUPPORTING, REFUTING, etc.)
   - Determine study weight based on publication type
   - Extract outcome measures if present
   - Store in database with reasoning
7. Track ruled-out hypotheses (2+ REFUTING citations from quality studies)
8. If depth < limit, spawn sub-subagents for highly relevant papers
9. Return summary with weighted consensus score

**Parameters**:
- `RESEARCH_QUESTION`: The clinical question
- `PAPER_ID`: PMID to analyze
- `DEPTH_LIMIT`: Max recursion (2-3)
- `CURRENT_DEPTH`: Current level
- `SESSION_ID`: Research session

### 8. Pattern Matching for Medical Classifications

Create comprehensive regex pattern lists in `classify_citations.py`:

**SUPPORTING patterns** (add to astronomy ones):
- r"demonstrated efficacy"
- r"showed? significant improvement"
- r"(reduced|decreased|lowered) (mortality|morbidity)"
- r"statistically significant benefit"
- r"superior to (placebo|control)"
- r"confirmed (safety|tolerability)"

**REFUTING patterns** (medical specific):
- r"failed to demonstrate"
- r"no significant (difference|benefit|effect)"
- r"non-inferior" (complex: could be positive!)
- r"(not|no) statistically significant"
- r"(adverse|serious) (event|effect)"
- r"(contraindicated|harmful) (in|for)"
- r"(withdrawn|recalled) (from|due to)"

**META_ANALYSIS patterns** (new category):
- r"meta-analysis (of|including)"
- r"systematic review (of|including)"
- r"pooled analysis"
- r"cochrane review"

**Study design detection patterns**:
- r"randomized controlled trial" → study_weight = 2.0
- r"double.?blind" → study_weight = 2.0
- r"meta.?analysis" → study_weight = 3.0
- r"case.?control" → study_weight = 1.0
- r"case report" → study_weight = 0.5

### 9. Configuration Files

**pyproject.toml** - Dependencies:
```toml
[project]
name = "medicus"
version = "0.1.0"
description = "Medical literature analysis with recursive subagents"
requires-python = ">=3.10"
dependencies = [
    "biopython>=1.80",        # PubMed access
    "requests>=2.28",          # HTTP
    "lxml>=4.9",               # XML parsing
    "pandas>=2.0",             # Data analysis
]
```

**CLAUDE.md** (project instructions):
```markdown
- Use `uv` to run python programs. Don't use `uv pip`, just use `uv run` and `uv add`
- In this repository, do not git commit any medical research outputs that you are asked to create. This repo is just for the definitions of skills and subagents and other infrastructure.
```

**SKILL.md** (Claude Code skill metadata):
```markdown
# med-literature

Search medical literature using PubMed, analyze citation networks with recursive subagents, and determine clinical consensus. Use when analyzing research questions about medical topics.
```

**examples.md** - Usage examples:
```markdown
# Example 1: Treatment Efficacy
"Is there consensus that metformin reduces cardiovascular mortality in type 2 diabetes?"

# Example 2: Drug Safety
"What is the current evidence on SGLT2 inhibitor safety in heart failure patients?"

# Example 3: Mechanism of Action
"What theories about the mechanism of action of GLP-1 agonists have been ruled out?"

# Example 4: Clinical Practice
"Is there consensus supporting early vs delayed antibiotic use in sepsis?"
```

### 10. Key Implementation Priorities

1. **Start with PubMed API integration** - This is the foundation
2. **Build the database schema** - Get the tables right first
3. **Create litdb.py CLI** - This is your primary interface
4. **Implement pattern-based classification** - Start simple, can improve later
5. **Build the subagent workflow** - Test with a single paper first
6. **Add recursion** - Once single-paper analysis works
7. **Implement weighted consensus** - The math for medical evidence
8. **Add trial registry lookup** - Nice to have, not critical for MVP

### 11. Testing Strategy

Create test cases using well-known medical examples:

**Test 1: Clear consensus**
- Question: "Does aspirin reduce cardiovascular events?"
- Expected: High positive consensus (0.7-0.9)
- Seed paper: Major aspirin trials (e.g., "Aspirin in primary prevention")

**Test 2: Ruled-out hypothesis**
- Question: "Is hormone replacement therapy cardioprotective in postmenopausal women?"
- Expected: Should find REFUTING citations from WHI trial
- Should track hypothesis as RULED_OUT

**Test 3: Active debate**
- Question: "Should vitamin D supplementation be routine?"
- Expected: Mixed consensus (-0.2 to 0.2)
- Should show CONTRASTING citations

### 12. Differences from Haruspex to Emphasize

**Astronomy → Medicine changes**:
- Bibcode → PMID (PubMed ID)
- ADS API → PubMed/Entrez API
- Astronomical objects → Clinical conditions/interventions
- Theoretical physics → Clinical evidence hierarchy
- SIMBAD/NED lookups → ClinicalTrials.gov lookups
- 6 classification types → 6 new medical classification types
- Flat citation weighting → Study-design-based weighting
- Keywords → MeSH terms

**Keep the same**:
- Overall architecture (recursive subagents)
- Database approach (SQLite)
- CLI-based tools
- Hypothesis tracking
- Consensus scoring formula (but weighted)
- Depth-limited recursion
- Session-based research tracking

## Deliverables

When you're done, I should have:

1. ✅ Complete project structure in a new `medicus` directory
2. ✅ Working PubMed API integration (`pubmed_search.py`)
3. ✅ Full medical database schema with tables created
4. ✅ Comprehensive CLI tool (`litdb.py`) with all commands
5. ✅ Citation classifier with medical patterns (`classify_citations.py`)
6. ✅ Subagent instruction template (`subagent-instructions.md`)
7. ✅ Working example with test case (aspirin or similar)
8. ✅ Documentation (`SKILL.md`, `examples.md`)
9. ✅ All dependencies configured with `uv` (`pyproject.toml`)

## Instructions

1. **Study haruspex first** - Read all the files to understand the patterns
2. **Create the new project structure** - Don't modify haruspex
3. **Build incrementally** - Test each component (API → DB → classifier → subagents)
4. **Follow the same patterns** - Use haruspex as your architectural guide
5. **Adapt, don't just copy** - Medical domain needs different classification logic
6. **Test with real data** - Use actual PubMed papers to validate

## Notes

- Keep the code clean and well-documented
- Use type hints in Python
- Make the CLI help text clear and useful
- Ensure database schema is normalized
- Pattern matching should be comprehensive but not overfitted
- Consensus scoring should make medical sense (RCTs matter more)

Begin by creating the project structure and implementing the PubMed API integration. Let me know when each major component is complete so I can test it.
