#!/usr/bin/env python3
"""
Citation Context Classifier

Analyzes citation contexts to classify the relationship between citing
and cited papers. Uses LLM-based classification for accurate understanding
of nuanced scientific language.

Classification is performed by gpt-4.1-mini by default, with regex-based
fallback when LLM is unavailable or explicitly disabled.

Citation Types:
- SUPPORTING: Agrees with, builds upon, confirms, or validates the cited work
- CONTRASTING: Disagrees with, challenges, questions, or presents alternatives
- REFUTING: Definitively rules out, provides strong evidence against hypothesis
- CONTEXTUAL: Provides background, general statements, historical context
- METHODOLOGICAL: References methods, data, tools, or techniques
- NEUTRAL: Simple acknowledgment without clear stance

Environment variables:
  OPENAI_API_KEY: Required for LLM classification
  LITDB_CLASSIFIER: "llm" (default) or "regex" to force regex-based classification
  LITDB_CLASSIFIER_MODEL: Model to use (default: gpt-4.1-mini)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional


# LLM Classification System Prompt
CLASSIFICATION_SYSTEM_PROMPT = """You are an expert in analyzing scientific literature, particularly in astronomy and astrophysics. Your task is to classify the relationship between a citing paper and a cited paper based on their abstracts.

Classification categories:
- SUPPORTING: The citing paper agrees with, confirms, validates, builds upon, or extends the cited work's findings or conclusions.
- CONTRASTING: The citing paper disagrees with, challenges, questions, or presents alternative interpretations to the cited work. There is tension but not definitive refutation.
- REFUTING: The citing paper provides strong evidence that definitively rules out, disproves, or renders obsolete the cited work's hypothesis or conclusions. This includes statistical exclusions (e.g., "ruled out at 5σ"), experimental refutations, or clear demonstrations that a theory is no longer viable.
- CONTEXTUAL: The citing paper references the cited work for background, historical context, general statements, or as a review without taking a stance.
- METHODOLOGICAL: The citing paper references the cited work for its methods, data, tools, techniques, software, or observational data without commenting on its conclusions.
- NEUTRAL: Simple acknowledgment or citation without any clear stance or relationship.

Important distinctions:
- REFUTING is stronger than CONTRASTING. REFUTING means the hypothesis/theory is ruled out; CONTRASTING means there is disagreement but the matter is not settled.
- Be particularly careful to identify REFUTING cases, as these are critical for understanding scientific consensus.
- Look for statistical language like "excluded at Xσ", "ruled out", "refuted", "no longer viable".

Respond with a JSON object containing:
- "classification": One of the six categories above
- "confidence": A number between 0 and 1 indicating your confidence
- "reasoning": A brief explanation of why you chose this classification"""


def get_openai_client():
    """Get OpenAI client, returns None if not available."""
    try:
        from openai import OpenAI
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return None
        return OpenAI(api_key=api_key)
    except ImportError:
        return None


def classify_with_llm(
    citing_abstract: str,
    cited_abstract: str,
    cited_title: str,
    model: str = None
) -> Tuple[str, float, str]:
    """
    Classify citation relationship using LLM.

    Returns tuple of (classification, confidence, reasoning)
    """
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI client not available. Set OPENAI_API_KEY or use --classifier=regex")

    model = model or os.environ.get('LITDB_CLASSIFIER_MODEL', 'gpt-4.1-mini')

    user_prompt = f"""Analyze the relationship between these two papers:

CITED PAPER:
Title: {cited_title or "Unknown"}
Abstract: {cited_abstract or "No abstract available"}

CITING PAPER (the paper that cites the above):
Abstract: {citing_abstract or "No abstract available"}

Based on the citing paper's abstract, classify its relationship to the cited paper."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Low temperature for consistent classification
            max_tokens=500
        )

        content = response.choices[0].message.content

        # Parse JSON response
        # Handle potential markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        result = json.loads(content.strip())

        classification = result.get('classification', 'NEUTRAL').upper()
        confidence = float(result.get('confidence', 0.5))
        reasoning = result.get('reasoning', 'LLM classification')

        # Validate classification
        valid_classifications = {'SUPPORTING', 'CONTRASTING', 'REFUTING',
                                 'CONTEXTUAL', 'METHODOLOGICAL', 'NEUTRAL'}
        if classification not in valid_classifications:
            classification = 'NEUTRAL'
            confidence = 0.3

        return classification, min(confidence, 0.99), reasoning

    except json.JSONDecodeError as e:
        # If JSON parsing fails, try to extract classification from text
        content = response.choices[0].message.content.upper()
        for cat in ['REFUTING', 'SUPPORTING', 'CONTRASTING', 'METHODOLOGICAL', 'CONTEXTUAL', 'NEUTRAL']:
            if cat in content:
                return cat, 0.5, f"Extracted from non-JSON response: {content[:100]}"
        return 'NEUTRAL', 0.3, f"Failed to parse LLM response: {str(e)}"
    except Exception as e:
        raise RuntimeError(f"LLM classification failed: {str(e)}")


# Fallback regex patterns for when LLM is not available

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

# Patterns indicating definitive refutation (stronger than contrast)
REFUTE_PATTERNS = [
    r'\b(rule[ds]?\s+out|ruled\s+out)\b',
    r'\b(exclude[ds]?|excluded)\b',
    r'\b(disprove[dns]?|disproven)\b',
    r'\b(refute[ds]?|refuted|refuting)\b',
    r'\b(reject[eds]?|rejected)\b',
    r'\bno\s+longer\s+(viable|tenable|valid)\b',
    r'\b(definitively|conclusively)\s+(shown|demonstrated|proved)\b',
    r'\b(incompatible|irreconcilable)\s+with\b',
    r'\b(inconsistent\s+at|excluded\s+at)\s+\d+\s*[σs]',  # e.g., "excluded at 5σ"
    r'\b>\s*\d+\s*[σs]\s+(exclusion|tension)',
    r'\b(firmly|strongly)\s+(excluded|ruled\s+out|rejected)\b',
    r'\b(abandoned|discarded|superseded)\b',
    r'\b(obsolete|outdated)\s+(model|theory|hypothesis)\b',
    r'\b(fatal|insurmountable)\s+(flaw|problem)\b',
    r'\b(cannot|could\s+not)\s+(explain|account\s+for)\b.*\bobserv',
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
        'REFUTING': 0,
        'METHODOLOGICAL': 0,
        'CONTEXTUAL': 0,
    }

    matched = {
        'SUPPORTING': [],
        'CONTRASTING': [],
        'REFUTING': [],
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

    # REFUTING patterns get double weight since they're more definitive
    for pattern in REFUTE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['REFUTING'] += 2
            matched['REFUTING'].append(pattern)

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

    # Boost confidence for REFUTING when patterns are strong
    if classification == 'REFUTING' and len(matched['REFUTING']) >= 2:
        confidence = min(confidence * 1.2, 0.95)

    return classification, min(confidence, 0.95), matched[classification]


def get_classifier_mode() -> str:
    """Get the classifier mode from environment."""
    return os.environ.get('LITDB_CLASSIFIER', 'llm').lower()


def analyze_abstract_relationship(
    citing_abstract: str,
    cited_abstract: str,
    cited_title: str,
    use_llm: bool = None
) -> Tuple[str, float, str]:
    """
    Analyze the relationship between a citing paper and cited paper
    based on their abstracts.

    Args:
        citing_abstract: Abstract of the citing paper
        cited_abstract: Abstract of the cited paper
        cited_title: Title of the cited paper
        use_llm: Whether to use LLM classification (default: from environment)

    Returns:
        Tuple of (classification, confidence, reasoning)
    """
    if not citing_abstract:
        return 'NEUTRAL', 0.0, "No citing abstract available"

    # Determine whether to use LLM
    if use_llm is None:
        use_llm = get_classifier_mode() == 'llm'

    if use_llm:
        try:
            return classify_with_llm(citing_abstract, cited_abstract, cited_title)
        except RuntimeError as e:
            # Fall back to regex if LLM fails
            print(f"Warning: LLM classification failed, falling back to regex: {e}",
                  file=sys.stderr)
            # Fall through to regex classification

    # Regex-based classification (fallback)
    # Check if cited paper's title/topic appears in citing abstract
    title_words = set(cited_title.lower().split()) if cited_title else set()
    common_stopwords = {'the', 'a', 'an', 'of', 'in', 'on', 'for', 'to', 'and', 'with'}
    title_words = title_words - common_stopwords

    abstract_words = set(citing_abstract.lower().split())
    overlap = title_words.intersection(abstract_words)

    # Classify based on patterns in citing abstract
    classification, confidence, patterns = classify_by_patterns(citing_abstract)

    reasoning = []
    reasoning.append("(regex fallback)")
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
        'REFUTING': 0,
        'CONTEXTUAL': 0,
        'METHODOLOGICAL': 0,
        'NEUTRAL': 0
    }

    high_confidence = []  # confidence > 0.7
    refuting_citations = []  # papers that refute

    for c in classifications:
        counts[c['classification']] += 1
        if c['confidence'] > 0.7:
            high_confidence.append(c)
        if c['classification'] == 'REFUTING':
            refuting_citations.append(c)

    total = len(classifications)
    percentages = {k: round(v / total * 100, 1) if total > 0 else 0
                   for k, v in counts.items()}

    result = {
        'total_citations': total,
        'counts': counts,
        'percentages': percentages,
        'high_confidence_count': len(high_confidence),
        'consensus_indicator': _calculate_consensus(counts, total),
        'refuting_count': len(refuting_citations),
    }

    # Flag if hypothesis appears to be ruled out
    if len(refuting_citations) >= 2:
        result['hypothesis_status'] = 'LIKELY_RULED_OUT'
    elif len(refuting_citations) == 1:
        result['hypothesis_status'] = 'POSSIBLY_RULED_OUT'
    else:
        result['hypothesis_status'] = 'ACTIVE'

    return result


def _calculate_consensus(counts, total):
    """
    Calculate a consensus indicator based on support vs contrast ratio.

    Returns a value from -1 (strong disagreement/refutation) to +1 (strong support)
    REFUTING counts double against since it's definitive.
    """
    if total == 0:
        return 0

    support = counts['SUPPORTING']
    contrast = counts['CONTRASTING']
    refuting = counts.get('REFUTING', 0)

    # Refuting counts double
    against = contrast + (refuting * 2)

    if support + against == 0:
        return 0  # No clear signals

    return round((support - against) / (support + against), 2)


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
  %(prog)s --classifier regex --input citations.json  # Force regex-based classification

Environment variables:
  OPENAI_API_KEY: Required for LLM classification
  LITDB_CLASSIFIER: "llm" (default) or "regex"
  LITDB_CLASSIFIER_MODEL: Model to use (default: gpt-4.1-mini)
        """
    )

    parser.add_argument('--input', '-i',
                        help='JSON file with citation network (from citation_analysis.py)')
    parser.add_argument('--citing-abstract',
                        help='Abstract of citing paper (for single classification)')
    parser.add_argument('--cited-abstract',
                        help='Abstract of cited paper (for single classification with LLM)')
    parser.add_argument('--cited-title',
                        help='Title of cited paper (for single classification)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--format', '-f', choices=['json', 'summary'],
                        default='summary', help='Output format')
    parser.add_argument('--classifier', '-c', choices=['llm', 'regex'],
                        default=None,
                        help='Classifier to use (default: from LITDB_CLASSIFIER env, or "llm")')
    parser.add_argument('--model', '-m',
                        help='LLM model to use (default: gpt-5.1-mini)')

    args = parser.parse_args()

    # Set classifier mode from argument if provided
    if args.classifier:
        os.environ['LITDB_CLASSIFIER'] = args.classifier
    if args.model:
        os.environ['LITDB_CLASSIFIER_MODEL'] = args.model

    # Single classification mode
    if args.citing_abstract:
        use_llm = get_classifier_mode() == 'llm'

        if use_llm:
            try:
                classification, confidence, reasoning = classify_with_llm(
                    args.citing_abstract,
                    args.cited_abstract or "",
                    args.cited_title or ""
                )
            except RuntimeError as e:
                print(f"LLM classification failed: {e}", file=sys.stderr)
                print("Falling back to regex classification...", file=sys.stderr)
                classification, confidence, reasoning = classify_by_patterns(args.citing_abstract)
                reasoning = reasoning if reasoning else []
        else:
            classification, confidence, reasoning = classify_by_patterns(args.citing_abstract)

        result = {
            'classification': classification,
            'confidence': confidence,
            'reasoning': reasoning if reasoning else 'No strong signals detected',
            'classifier': 'llm' if use_llm else 'regex'
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

    refuting_marker = " ⚠️" if counts.get('REFUTING', 0) > 0 else ""

    lines.extend([
        f"  SUPPORTING:     {counts['SUPPORTING']:4d} ({pcts['SUPPORTING']:5.1f}%)",
        f"  CONTRASTING:    {counts['CONTRASTING']:4d} ({pcts['CONTRASTING']:5.1f}%)",
        f"  REFUTING:       {counts.get('REFUTING', 0):4d} ({pcts.get('REFUTING', 0):5.1f}%){refuting_marker}",
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
        consensus_text = "Significant disagreement/refutation in the literature"
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

    # REFUTING citations section (shown before CONTRASTING since more important)
    refuting = [c for c in data['classifications']
                if c['classification'] == 'REFUTING']

    if refuting:
        lines.extend([
            "",
            "-" * 70,
            "⚠️  REFUTING CITATIONS (HYPOTHESIS MAY BE RULED OUT)",
            "-" * 70,
        ])

        refuting.sort(key=lambda x: x['confidence'], reverse=True)

        for c in refuting:
            lines.append(f"  [{c['confidence']:.2f}] {c['citing_title'][:60]}...")
            lines.append(f"         {c['citing_bibcode']} ({c['citing_year']})")
            if c.get('reasoning'):
                lines.append(f"         Reason: {c['reasoning'][:50]}...")

        # Hypothesis status warning
        hypothesis_status = data['summary'].get('hypothesis_status', 'ACTIVE')
        if hypothesis_status == 'LIKELY_RULED_OUT':
            lines.append("")
            lines.append("  ⚠️  Multiple refuting citations found!")
            lines.append("      This hypothesis appears to have been RULED OUT.")
        elif hypothesis_status == 'POSSIBLY_RULED_OUT':
            lines.append("")
            lines.append("  ⚠️  Refuting citation found - verify hypothesis status.")

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
