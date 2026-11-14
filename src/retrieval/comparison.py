"""Resolve fully specified record comparisons. Ambiguous requests stay on search."""
import re
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class Comparison:
    collection: str
    ids: tuple[str, str]
    labels: tuple[str, str]
    field: str


def parse_comparison(question):
    if not re.search(r'\b(compare|comparison|difference|higher|lower)\b', question, re.I):
        return None
    def terms(pattern):
        return re.findall(pattern, question, re.I)
    traits = terms(r'\b(2hrG)\b')
    if len(traits) != 1:
        return None
    fields = terms(r'\b(enrichment_beta|h2_beta|coefficient_beta|diff_beta|pValue|beta)\b')
    if len(fields) != 1:
        return None
    field = 'pValue' if fields[0].lower() == 'pvalue' else fields[0].lower()
    if re.search(r'\bWES\b', question, re.I):
        genes = terms(r'\bgene\s+([\w.-]+)')
        masks = terms(r'\bmask\s+([\w.-]+)')
        if len(genes) != 1 or field not in {'pValue','beta'}:
            return None
        labels = (['summary'] if re.search(r'\bsummary\b', question, re.I) else []) + [m.rstrip('.') for m in masks]
        if len(labels) != 2 or len(set(labels)) != 2:
            return None
        stem = 'wes:2hrG:' + quote(genes[0].rstrip('.'), safe='') + ':'
        ids = tuple(stem + ('summary' if label == 'summary' else 'mask:' + quote(label, safe='')) for label in labels)
        return Comparison('gene_association_wes', ids, tuple(labels), field)
    keys = []
    for key in ('annotation','tissue','biosample'):
        matches = terms(r'\b' + key + r'\s+([\w.-]+|\[(?:null|missing)\])')
        if len(matches) != 1:
            return None
        value = matches[0].rstrip('.')
        keys.append(value if value in {'[null]', '[missing]'} else quote(value, safe=''))
    labels = re.findall(r'\b(EA|EU|HS|Mixed)\b', question)
    if len(labels) != 2 or len(set(labels)) != 2 or field == 'beta':
        return None
    stem = ':'.join(['ldsc_partitioned','2hrG',*keys,''])
    return Comparison('ldsc_partitioned_heritability', tuple(stem + s for s in labels), tuple(labels), field)
