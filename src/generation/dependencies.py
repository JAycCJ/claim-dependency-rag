"""Record-bound numeric facts and deterministic two-record comparisons."""
from math import isfinite

from generation.schema import Claim, Derived, Fact, GeneratedAnswer
from generation.numeric_validation import NUMBER
from retrieval.comparison import parse_comparison


def source_value(passage, field):
    metadata = passage.metadata
    if passage.collection == 'gene_association_wes':
        key = 'raw_mask' if metadata.get('record_kind') == 'mask_result' else 'raw_parent'
        metadata = metadata.get(key, {})
    value = metadata.get(field)
    if value is None:
        values = {float(m['number']) for m in NUMBER.finditer(passage.content) if m['field'].lower() == field.lower()}
        value = values.pop() if len(values) == 1 else None
    return value if type(value) in (int, float) and isfinite(value) else None


def comparison(left, right):
    relation = 'higher than' if left.value > right.value else 'lower than' if left.value < right.value else 'equal to'
    return Derived('compare', (left, right), relation, left.value - right.value)


def fact_text(fact, label):
    return f'{label}: {fact.field}={fact.value}.'


def derived_text(derived, labels):
    a, b = derived.operands
    return f'{labels[0]} ({a.value}) is {derived.relation} {labels[1]} ({b.value}) for {a.field}. Difference (first minus second): {derived.difference}.'


def generate_comparison(context):
    plan = parse_comparison(context.question)
    if plan is None or plan.collection not in context.effective_collections:
        return None
    # Preserve the pipeline's refusal policy for individual medical questions.
    if context.evidence_status == 'refuse' and any('individual medical advice' in s for s in context.limitations):
        return None
    passages = {p.chunk_id: p for p in context.passages if p.collection == plan.collection}
    facts, claims, missing = [], [], []
    limits = list(context.limitations)
    for cid, label in zip(plan.ids, plan.labels):
        value = source_value(passages[cid], plan.field) if cid in passages else None
        if value is None:
            missing.append(cid)
            limits.append(f'Missing {label} record or field ({cid}, {plan.field}); cannot compare.')
            continue
        fact = Fact(cid, plan.field, value)
        facts.append(fact)
        claims.append(Claim(fact_text(fact, label), [cid], fact=fact, depends_on=[cid]))
    if len(facts) == 2:
        derived = comparison(*facts)
        claims.append(Claim(derived_text(derived, plan.labels), list(plan.ids), derived=derived, depends_on=list(plan.ids)))
    ids = [f.chunk_id for f in facts]
    diagnostics = {'missing_dependencies': missing, 'target_ids': list(plan.ids)}
    if plan.collection == 'gene_association_wes':
        diagnostics['wes_evidence_groups'] = len({passages[c].metadata['group_id'] for c in ids})
        limits.append('Masks from the same gene group are not independent evidence. Cross-collection independence is unknown.')
    return GeneratedAnswer('qualified' if claims and limits else 'answer' if claims else 'refuse',
        '\n\n'.join(c.text for c in claims) or 'I cannot answer this question from the authorized approved corpus.',
        claims, [passages[c].citation for c in ids], limits, provider='claim_dependency', diagnostics=diagnostics)


def retract(answer, context):
    """Recompute the original comparison using only its surviving records."""
    if answer.provider != 'claim_dependency':
        raise ValueError('Retraction requires a structured comparison')
    plan = parse_comparison(context.question)
    if plan is None or tuple(answer.diagnostics.get('target_ids', ())) != plan.ids:
        raise ValueError('Changed context must refer to the original comparison')
    return generate_comparison(context)


def dependency_errors(answer, context):
    if not any(c.depends_on is not None or c.fact or c.derived for c in answer.claims) and answer.provider != 'claim_dependency':
        return []
    expected = generate_comparison(context)
    if expected is None or answer.claims != expected.claims or answer.citations != expected.citations:
        return ['structured claims differ from recomputed source records, dependencies or citations']
    return []
