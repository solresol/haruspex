#!/usr/bin/env python3
"""
Citation Context Classifier

Analyzes citation contexts to classify the relationship between citing
and cited papers. Uses heuristics based on abstract analysis when full
text is not available.

Citation Types:
- SUPPORTING: Agrees with, builds upon, confirms, or validates the cited work
- CONTRASTING: Disagrees with, challenges, questions, or presents alternatives
- CONTEXTUAL: Provides background, general statements, historical context
- METHODOLOGICAL: References methods, data, tools, or techniques
- NEUTRAL: Simple acknowledgment without clear stance
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Patterns indicating support for cited work
SUPPORT_PATTERNS = [
    r'\b(confirm|confirmed|confirms)\b',
    r'\b(agree|agreed|agrees|agreement)\b',
    r'\b(consistent|consistency)\s+with\b',
    r'\b(support|supported|supports|supporting)\b',
    r'\b(validate|validated|validates|validation)\b',
    r'\b(verify|verified|verifies|verification)\b',
    r'\b(in\s+line\s+with)\b',
    r'\b(corroborate|corroborated)\b',
    r'\b(extend|extended|extends|extending)\b',
    r'\b(build|built|builds)\s+(on|upon)\b',
    r'\b(reinforce|reinforced)\b',
    r'\b(demonstrate|demonstrated|demonstrates)\b.*\bsame\b',
    r'\bas\s+(shown|found|demonstrated|reported)\s+by\b',
    r'\b(similar\s+to|similar\s+results)\b',
]

# Patterns indicating contrast or disagreement
CONTRAST_PATTERNS = [
    r'\b(disagree|disagreed|disagrees|disagreement)\b',
    r'\b(contradict|contradicted|contradicts|contradiction)\b',
    r'\b(inconsistent|inconsistency)\b',
    r'\b(challenge|challenged|challenges|challenging)\b',
    r'\b(question|questioned|questions)\b',
    r'\b(contrary|contrast)\s+to\b',
    r'\b(unlike|different\s+from)\b',
    r'\b(however|although|but|yet)\b.*\b(found|showed|reported)\b',
    r'\b(alternative|alternatively)\b',
    r'\b(revise|revised|revises|revision)\b',
    r'\b(tension|discrepancy)\b',
    r'\b(not\s+support|does\s+not\s+support|do\s+not\s+support)\b',
    r'\b(failed\s+to|fails\s+to)\s+(confirm|reproduce|replicate)\b',
    r'\b(overestimate|underestimate)\b',
    r'\b(at\s+odds\s+with)\b',
]

# Patterns indicating methodological reference
METHOD_PATTERNS = [
    r'\b(method|methods|methodology)\b.*\b(described|developed|introduced)\s+by\b',
    r'\b(technique|techniques)\b.*\bfrom\b',
    r'\b(code|software|pipeline|algorithm)\b.*\b(from|by)\b',
    r'\b(data|catalog|survey)\b.*\b(from|by)\b',
    r'\b(following|follow)\s+the\s+(method|approach|procedure)\b',
    r'\b(using|used|use)\s+the\s+(method|code|software)\b',
    r'\b(adopted|adopt|adopting)\s+(from|the\s+method)\b',
    r'\bas\s+(implemented|described)\s+in\b',
]

# Patterns indicating contextual/background reference
CONTEXT_PATTERNS = [
    r'\b(see|e\.g\.|for\s+example|for\s+instance)\b',
    r'\b(review|reviews|reviewed)\s+(in|by)\b',
    r'\b(discovered|first\s+reported)\s+by\b',
    r'\b(originally|initially)\s+(proposed|suggested)\b',
    r'\b(well[\s-]known|well[\s-]established)\b',
    r'\b(theoretical\s+framework|model)\s+(of|from|by)\b',
    r'\b(history|historical|historically)\b',
    r'\b(seminal|pioneering|landmark)\b',
]


def classify_by_patterns(text):
    """
    Classify citation context based on linguistic patterns.

    Returns tuple of (classification, confidence, matched_patterns)
    """
    if not text:
        return 'NEUTRAL', 0.0, []

    text = text.lower()

    scores = {
        'SUPPORTING': 0,
        'CONTRASTING': 0,
        'METHODOLOGICAL': 0,
        'CONTEXTUAL': 0,
    }

    matched = {
        'SUPPORTING': [],
        'CONTRASTING': [],
        'METHODOLOGICAL': [],
        'CONTEXTUAL': [],
    }

    for pattern in SUPPORT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['SUPPORTING'] += 1
            matched['SUPPORTING'].append(pattern)

    for pattern in CONTRAST_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['CONTRASTING'] += 1
            matched['CONTRASTING'].append(pattern)

    for pattern in METHOD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['METHODOLOGICAL'] += 1
            matched['METHODOLOGICAL'].append(pattern)

    for pattern in CONTEXT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['CONTEXTUAL'] += 1
            matched['CONTEXTUAL'].append(pattern)

    # Find highest score
    max_score = max(scores.values())
    if max_score == 0:
        return 'NEUTRAL', 0.0, []

    # Get the classification with highest score
    classification = max(scores.keys(), key=lambda k: scores[k])

    # Calculate confidence based on score differential
    total_matches = sum(scores.values())
    confidence = scores[classification] / total_matches if total_matches > 0 else 0

    # Lower confidence if there are competing signals
    second_highest = sorted(scores.values(), reverse=True)[1]
    if second_highest > 0 and second_highest >= max_score * 0.7:
        confidence *= 0.6  # Reduce confidence when signals are mixed

    return classification, min(confidence, 0.95), matched[classification]


def analyze_abstract_relationship(citing_abstract, cited_abstract, cited_title):
    """
    Analyze the relationship between a citing paper and cited paper
    based on their abstracts.
    """
    if not citing_abstract:
        return 'NEUTRAL', 0.0, "No citing abstract available"

    # Check if cited paper's title/topic appears in citing abstract
    title_words = set(cited_title.lower().split()) if cited_title else set()
    common_stopwords = {'the', 'a', 'an', 'of', 'in', 'on', 'for', 'to', 'and', 'with'}
    title_words = title_words - common_stopwords

    abstract_words = set(citing_abstract.lower().split())
    overlap = title_words.intersection(abstract_words)

    # Classify based on patterns in citing abstract
    classification, confidence, patterns = classify_by_patterns(citing_abstract)

    reasoning = []
    if patterns:
        reasoning.append(f"Matched patterns: {len(patterns)}")
    if overlap:
        reasoning.append(f"Topic overlap: {', '.join(list(overlap)[:5])}")

    return classification, confidence, '; '.join(reasoning) if reasoning else "No strong signals"


def classify_citation(citing_paper, cited_paper):
    """
    Classify the citation relationship between two papers.

    Args:
        citing_paper: Dict with keys 'bibcode', 'title', 'abstract', etc.
        cited_paper: Dict with keys 'bibcode', 'title', 'abstract', etc.

    Returns:
        Dict with classification results
    """
    classification, confidence, reasoning = analyze_abstract_relationship(
        citing_paper.get('abstract'),
        cited_paper.get('abstract'),
        cited_paper.get('title')
    )

    return {
        'citing_bibcode': citing_paper.get('bibcode'),
        'citing_title': citing_paper.get('title'),
        'citing_year': citing_paper.get('year'),
        'cited_bibcode': cited_paper.get('bibcode'),
        'cited_title': cited_paper.get('title'),
        'classification': classification,
        'confidence': round(confidence, 3),
        'reasoning': reasoning
    }


def aggregate_classifications(classifications):
    """Aggregate classification results into summary statistics."""
    counts = {
        'SUPPORTING': 0,
        'CONTRASTING': 0,
        'CONTEXTUAL': 0,
        'METHODOLOGICAL': 0,
        'NEUTRAL': 0
    }

    high_confidence = []  # confidence > 0.7
    controversial = []  # papers with both support and contrast

    for c in classifications:
        counts[c['classification']] += 1
        if c['confidence'] > 0.7:
            high_confidence.append(c)

    total = len(classifications)
    percentages = {k: round(v / total * 100, 1) if total > 0 else 0
                   for k, v in counts.items()}

    return {
        'total_citations': total,
        'counts': counts,
        'percentages': percentages,
        'high_confidence_count': len(high_confidence),
        'consensus_indicator': _calculate_consensus(counts, total)
    }


def _calculate_consensus(counts, total):
    """
    Calculate a consensus indicator based on support vs contrast ratio.

    Returns a value from -1 (strong disagreement) to +1 (strong support)
    """
    if total == 0:
        return 0

    support = counts['SUPPORTING']
    contrast = counts['CONTRASTING']

    if support + contrast == 0:
        return 0  # No clear signals

    return round((support - contrast) / (support + contrast), 2)


def load_citations(input_file):
    """Load citations from JSON file."""
    with open(input_file) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description='Classify citation relationships in astronomical papers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input citations.json
  %(prog)s --input network.json --output classified.json
  %(prog)s --citing-abstract "We confirm the findings of..." --cited-title "Dark matter study"
        """
    )

    parser.add_argument('--input', '-i',
                        help='JSON file with citation network (from citation_analysis.py)')
    parser.add_argument('--citing-abstract',
                        help='Abstract of citing paper (for single classification)')
    parser.add_argument('--cited-title',
                        help='Title of cited paper (for single classification)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--format', '-f', choices=['json', 'summary'],
                        default='summary', help='Output format')

    args = parser.parse_args()

    # Single classification mode
    if args.citing_abstract:
        classification, confidence, reasoning = classify_by_patterns(args.citing_abstract)
        result = {
            'classification': classification,
            'confidence': confidence,
            'reasoning': reasoning if reasoning else 'No strong signals detected'
        }
        print(json.dumps(result, indent=2))
        return

    # Batch mode from file
    if not args.input:
        parser.error("Either --input or --citing-abstract is required")

    # Load citation network
    data = load_citations(args.input)

    # Handle output from citation_analysis.py
    if 'target_paper' in data:
        cited_paper = data['target_paper']
        citing_papers = data.get('citing_papers', [])
    else:
        print("Error: Unrecognized input format", file=sys.stderr)
        sys.exit(1)

    # Classify each citation
    classifications = []
    for citing in citing_papers:
        result = classify_citation(citing, cited_paper)
        classifications.append(result)

    # Aggregate results
    summary = aggregate_classifications(classifications)

    output_data = {
        'cited_paper': {
            'bibcode': cited_paper.get('bibcode'),
            'title': cited_paper.get('title')
        },
        'summary': summary,
        'classifications': classifications
    }

    # Format output
    if args.format == 'json':
        output = json.dumps(output_data, indent=2)
    else:
        output = format_summary_output(output_data)

    # Write output
    if args.output:
        Path(args.output).write_text(output)
        print(f"Classification results written to {args.output}", file=sys.stderr)
    else:
        print(output)


def format_summary_output(data):
    """Format classification results as human-readable summary."""
    lines = [
        "=" * 70,
        "CITATION CLASSIFICATION ANALYSIS",
        "=" * 70,
        "",
        f"Cited Paper: {data['cited_paper']['title']}",
        f"Bibcode: {data['cited_paper']['bibcode']}",
        "",
        "-" * 70,
        "CLASSIFICATION SUMMARY",
        "-" * 70,
        f"Total citations analyzed: {data['summary']['total_citations']}",
        "",
    ]

    counts = data['summary']['counts']
    pcts = data['summary']['percentages']

    lines.extend([
        f"  SUPPORTING:     {counts['SUPPORTING']:4d} ({pcts['SUPPORTING']:5.1f}%)",
        f"  CONTRASTING:    {counts['CONTRASTING']:4d} ({pcts['CONTRASTING']:5.1f}%)",
        f"  CONTEXTUAL:     {counts['CONTEXTUAL']:4d} ({pcts['CONTEXTUAL']:5.1f}%)",
        f"  METHODOLOGICAL: {counts['METHODOLOGICAL']:4d} ({pcts['METHODOLOGICAL']:5.1f}%)",
        f"  NEUTRAL:        {counts['NEUTRAL']:4d} ({pcts['NEUTRAL']:5.1f}%)",
        "",
    ])

    consensus = data['summary']['consensus_indicator']
    if consensus > 0.5:
        consensus_text = "Strong support in the literature"
    elif consensus > 0.2:
        consensus_text = "Generally supported"
    elif consensus < -0.5:
        consensus_text = "Significant disagreement in the literature"
    elif consensus < -0.2:
        consensus_text = "Some disagreement present"
    else:
        consensus_text = "Mixed or neutral reception"

    lines.extend([
        f"Consensus Indicator: {consensus:+.2f} ({consensus_text})",
        f"High-confidence classifications: {data['summary']['high_confidence_count']}",
        "",
        "-" * 70,
        "TOP SUPPORTING CITATIONS",
        "-" * 70,
    ])

    supporting = [c for c in data['classifications']
                  if c['classification'] == 'SUPPORTING']
    supporting.sort(key=lambda x: x['confidence'], reverse=True)

    for c in supporting[:5]:
        lines.append(f"  [{c['confidence']:.2f}] {c['citing_title'][:60]}...")
        lines.append(f"         {c['citing_bibcode']} ({c['citing_year']})")

    lines.extend([
        "",
        "-" * 70,
        "TOP CONTRASTING CITATIONS",
        "-" * 70,
    ])

    contrasting = [c for c in data['classifications']
                   if c['classification'] == 'CONTRASTING']
    contrasting.sort(key=lambda x: x['confidence'], reverse=True)

    for c in contrasting[:5]:
        lines.append(f"  [{c['confidence']:.2f}] {c['citing_title'][:60]}...")
        lines.append(f"         {c['citing_bibcode']} ({c['citing_year']})")

    if not contrasting:
        lines.append("  (No contrasting citations detected)")

    return '\n'.join(lines)


if __name__ == '__main__':
    main()
