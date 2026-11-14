"""Freeze entity-disjoint comparison prompts. Only IDs are read for exclusion."""
import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/evaluation'
OUT = DATA / 'ablation'
SEED = 61113


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group(cid):
    if cid.startswith('wes:'):
        return ':'.join(cid.split(':')[:3])
    return cid.rsplit(':', 1)[0]


def records():
    for name in ['ldsc_partitioned_2hrG', 'wes_2hrG']:
        with (ROOT / f'artifacts/chunks/{name}.chunks.jsonl').open() as f:
            for line in f:
                yield json.loads(line)


def build():
    if any(OUT.glob('*.json*')):
        raise SystemExit('Frozen outputs already exist')
    rng = random.Random(SEED)
    excluded = set()
    genes = set()
    def visit(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ('gene', 'gene_symbol') and isinstance(x, str):
                    genes.add(x.upper())
                visit(x)
        elif isinstance(v, list):
            for x in v:
                visit(x)
        elif isinstance(v, str):
            if re.fullmatch(r'(ldsc_partitioned|wes):[^\s]+', v):
                excluded.add(group(v))
            if re.fullmatch(r'(gene_info|gene_common|gene_rare|gtex|gene_association_common|gene_association_rare):[^\s]+', v):
                genes.update(v.upper().split(':')[1:])
            genes.update(re.findall(r'\b[A-Z][A-Z0-9-]{1,}\b', v))
    for path in sorted(DATA.rglob('*.jsonl')):
        for line in path.read_text().splitlines():
            visit(json.loads(line))
    groups = defaultdict(list)
    for r in records():
        g = group(r['chunk_id'])
        if g not in excluded and r['metadata'].get('gene','').upper() not in genes:
            groups[g].append(r['chunk_id'])
    pools = defaultdict(list)
    for g, ids in sorted(groups.items()):
        if g.startswith('wes:'):
            masks = sorted(i for i in ids if ':mask:' in i)
            if len(masks) < 2:
                continue
            b, distractor = rng.sample(masks, 2)
            a = g + ':summary'
            gene = unquote(g.split(':')[-1])
            field = rng.choice(['pValue','beta'])
            q = f'For WES 2hrG gene {gene}, compare {field} between summary and mask {unquote(b.split(":")[-1])}.'
            kind = 'wes'
        else:
            _, pheno, ann, tissue, sample = g.split(':')
            if not all(re.fullmatch(r'[\w.-]+|\[(null|missing)\]', unquote(x)) for x in (ann,tissue,sample)):
                continue
            if not {g+':EA',g+':EU',g+':HS',g+':Mixed'}.issubset(ids):
                continue
            left, right = rng.sample(['EA','EU','HS','Mixed'],2)
            distractors = sorted({'HS','Mixed'}-{left,right})
            if not distractors:
                continue
            a,b,distractor = [g+':'+x for x in (left,right,rng.choice(distractors))]
            field = rng.choice(['enrichment_beta','h2_beta','coefficient_beta','diff_beta'])
            q = f'For LDSC {pheno}, annotation {unquote(ann)}, tissue {unquote(tissue)}, biosample {unquote(sample)}, compare {field} between {left} and {right}.'
            kind = 'ldsc'
        pools[kind].append(dict(question=q,kind=kind,field=field,ids=[a,b],distractor=distractor))
    for rows in pools.values():
        rng.shuffle(rows)
    OUT.mkdir(exist_ok=True)
    manifest = {'seed':SEED,'splits':{}}
    for split, parts in [('dev',(20,8)),('evaluation',(200,40))]:
        rows = []
        for kind,n in zip(('ldsc','wes'),parts):
            if len(pools[kind]) < n:
                raise ValueError(f'Insufficient eligible {kind} groups')
            rows.extend(pools[kind][:n])
            del pools[kind][:n]
        path = OUT / (split+'.jsonl')
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        manifest['splits'][split] = dict(questions=len(rows),sha256=digest(path))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__ == '__main__':
    build()
