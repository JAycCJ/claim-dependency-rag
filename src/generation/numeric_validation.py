"""Check explicitly labelled scientific numbers against their cited evidence.

This deterministic check catches numeric fabrication; it is not an entailment judge.
Rounded source displays are accepted at 5e-4 relative tolerance (four significant digits).
"""

from __future__ import annotations
import math
import re
from augmentation.schema import ContextPackage
from generation.schema import GeneratedAnswer

NUMBER = re.compile(
    r"(?P<field>pValue|p[- ]value|mixed_pvalue|mixed_rg|bf_common|bf_rare|enrichment_beta|h2_beta|stdErr|median|beta|rg|z|p)\s*(?:=|:|\bis\b|\bwas\b|\bof\b)\s*(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.I,
)
ALIASES = {"p": "pvalue", "p-value": "pvalue", "p value": "pvalue", "rg": "mixed_rg"}


def fields(value):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
            ):
                result.setdefault(key.lower(), []).append(float(item))
            elif isinstance(item, (dict, list)):
                for field, numbers in fields(item).items():
                    result.setdefault(field, []).extend(numbers)
    elif isinstance(value, list):
        for item in value:
            for field, numbers in fields(item).items():
                result.setdefault(field, []).extend(numbers)
    return result


# Only explicit, ordered subtraction has an unambiguous sign.
DIFFERENCE_PREFIX = re.compile(
    r"\b(EA|EU|HS|Mixed)[- ]minus[- ](EA|EU|HS|Mixed)\s+difference\s+in\s+(?:reported\s+)?$",
    re.I,
)


BY_DIFFERENCE = re.compile(
    r"\b(EA|EU|HS|Mixed)\s+(?:is|was)\s+(higher|lower)\s+than\s+"
    r"(EA|EU|HS|Mixed)\s+by\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", re.I,
)


def difference_candidate(labels, field, citations, passages, question):
    from retrieval.comparison import parse_comparison
    plan = parse_comparison(question)
    if not plan or (field is not None and field != plan.field.lower()) or set(citations) != set(plan.ids):
        return []
    values = {}
    for cid, label in zip(plan.ids, plan.labels):
        passage = passages.get(cid)
        if not passage or passage.collection != plan.collection:
            return []
        value = passage.metadata.get(plan.field)
        if type(value) not in (float, int) or not math.isfinite(value):
            return []
        values[label.lower()] = value
    left, right = (label.lower() for label in labels)
    if left == right or left not in values or right not in values:
        return []
    return [values[left] - values[right]]


def numeric_errors(answer: GeneratedAnswer, context: ContextPackage) -> list[str]:
    passages = {p.chunk_id: p for p in context.passages}
    errors = []
    claims = [(claim.text, claim.citations) for claim in answer.claims]
    # validate_answer checks that the body consists entirely of its cited claims.
    joined = "\n\n".join(c.text for c in answer.claims)
    prefix = answer.answer.removesuffix(joined) if joined else answer.answer
    if NUMBER.search(prefix) or BY_DIFFERENCE.search(prefix):
        claims.append((prefix, list(dict.fromkeys(cid for c in answer.claims for cid in c.citations))))
    for text, citations in claims:
        for match in BY_DIFFERENCE.finditer(text):
            left, direction, right, magnitude = match.groups()
            labels = (left, right) if direction.lower() == "higher" else (right, left)
            values = difference_candidate(labels, None, citations, passages, context.question)
            if not any(v > 0 and math.isclose(float(magnitude), v, rel_tol=5e-4) for v in values):
                errors.append("unsupported ordered difference: " + match.group())
        expected = {}
        for cid in citations:
            if cid not in passages:
                continue
            passage = passages[cid]
            for field, numbers in fields(passage.metadata).items():
                expected.setdefault(field, []).extend(numbers)
            for match in NUMBER.finditer(passage.content):
                key = ALIASES.get(match["field"].lower(), match["field"].lower())
                expected.setdefault(key, []).append(float(match["number"]))
        for match in NUMBER.finditer(text):
            key = ALIASES.get(match["field"].lower(), match["field"].lower())
            number = float(match["number"])
            # p and rg may be supplied under Mixed ancestry names by the offline generator.
            candidates = expected.get(key, [])
            if key == "pvalue":
                candidates += expected.get("mixed_pvalue", [])
            order = DIFFERENCE_PREFIX.search(text[:match.start()])
            if order:
                candidates = difference_candidate(order.groups(), key, citations, passages, context.question)
            if not any(
                math.isclose(number, truth, rel_tol=5e-4, abs_tol=1e-300)
                for truth in candidates
            ):
                errors.append(
                    f"unsupported numeric value: {match['field']}={match['number']}"
                )
    return list(dict.fromkeys(errors))
