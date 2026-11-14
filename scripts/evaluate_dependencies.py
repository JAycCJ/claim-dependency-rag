"""Run paired, fixed-context ablations without loading .env or making paid calls."""
import argparse
import json
import math
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from build_dependency_ablation import OUT, ROOT, digest, records

sys.path.insert(0,str(ROOT/'src'))
from augmentation.schema import ContextPackage, EvidencePassage
from generation.dependencies import generate_comparison
from generation.offline import OfflineEvidenceGenerator
from generation.validator import validate_answer

REPORT = ROOT/'reports/phase_6_claim_dependency'
NUMBER = r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?'


def fixed_context(q, ids, corpus):
    passages = []
    for rank,cid in enumerate(ids,1):
        row = corpus[cid]
        passages.append(EvidencePassage(cid,row['collection'],rank,1.,row['title'],row['content'],row['metadata'],row['citation']))
    allowed = [passages[0].collection]
    return ContextPackage(q,allowed,allowed,'specified',passages,{p.chunk_id:p.citation for p in passages},
                          'qualified',['Source field definitions unconfirmed.'],0,1800)


def gold_value(row, field):
    m = row['metadata']
    if row['collection'] == 'gene_association_wes':
        m = m['raw_mask'] if 'raw_mask' in m else m['raw_parent']
    return m[field]


def score(answer, row, corpus, condition, original):
    a,b = row['ids']
    labels = [cid.split(':')[-1] for cid in (a,b)]
    field = row['field']
    va,vb = [gold_value(corpus[i],field) for i in (a,b)]
    expected = 'higher' if va > vb else 'lower' if va < vb else 'equal'
    def names(text, label):
        return re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',text,re.I)
    def reports(claim, cid, label, value):
        return cid in claim.citations and names(claim.text,label) and any(
            math.isclose(float(n),value,rel_tol=5e-4,abs_tol=1e-300)
            for n in re.findall(r'\b'+field+r'\s*[=:]\s*('+NUMBER+')',claim.text,re.I))
    relations = [c for c in answer.claims if all(names(c.text,l) for l in labels) and
                 re.search(r'\b(higher|lower|greater|less|equal|exceeds)\b',c.text,re.I)]
    cited = {i for c in answer.claims for i in c.citations}
    complete = condition in ('C1','C4')
    facts = [any(reports(c,i,l,v) for c in answer.claims) for i,l,v in zip((a,b),labels,(va,vb))]
    metrics = {}
    if complete:
        metrics['correct_comparison'] = all(facts) and any(expected in c.text.lower() and c.text.lower().index(labels[0].lower()) < c.text.lower().index(labels[1].lower())
            and set(c.citations)=={a,b} for c in relations)
    else:
        metrics['unsupported_comparison'] = bool(relations)
        metrics['retained_fact'] = facts[0]
        metrics['named_missing'] = any(names(t,labels[1]) and re.search(r'missing|lack|unavailable',t,re.I)
            for t in [*answer.limitations,*(c.text for c in answer.claims)])
    if condition == 'C3':
        d = row['distractor']
        metrics['substitution'] = any(d in c.citations for c in relations) or any(
            reports(c,d,labels[1],gold_value(corpus[d],field)) for c in answer.claims)
    signature = [(c.text,c.citations) for c in relations]
    if condition == 'C4':
        metrics['restored_comparison'] = bool(signature) and signature == original
    if row['kind']=='wes':
        gold = {a,b} if complete else {a}
        metrics['exact_citations'] = cited == gold
        metrics['citation_precision'] = len(cited & gold)/len(cited) if cited else 0
        metrics['citation_recall'] = len(cited & gold)/len(gold)
        metrics['correct_group_count'] = answer.diagnostics.get('wes_evidence_groups') == 1
    return signature, metrics


def interval(values):
    n = len(values)
    avg = statistics.mean(values)
    if set(values)<= {0,1}:
        z = 1.95996398454
        base = 1+z*z/n
        mid = (avg+z*z/(2*n))/base
        rad = z*math.sqrt(avg*(1-avg)/n+z*z/(4*n*n))/base
        return [avg,max(0,mid-rad),min(1,mid+rad),n,'Wilson']
    import numpy as np
    sims = np.random.default_rng(61113).choice(values,(10000,n)).mean(axis=1)
    return [avg,*map(float,np.quantile(sims,[.025,.975])),n,'bootstrap']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split',choices=['dev','evaluation'],default='evaluation')
    args = parser.parse_args()
    path = OUT/(args.split+'.jsonl')
    assert digest(path)==json.loads((OUT/'manifest.json').read_text())['splits'][args.split]['sha256']
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    ids = {i for r in rows for i in [*r['ids'],r['distractor']]}
    corpus = {r['chunk_id']:r for r in records() if r['chunk_id'] in ids}
    results, buckets, paired = [], defaultdict(list), defaultdict(dict)
    offline = OfflineEvidenceGenerator()
    for i,r in enumerate(rows):
        a,b = r['ids']
        original = {}
        for cond,evidence in [('C1',[a,b]),('C2',[a]),('C3',[a,r['distractor']]),('C4',[b,a])]:
            context = fixed_context(r['question'], evidence, corpus)
            for mode,fn in [('baseline_B',offline.generate),('dependency',generate_comparison)]:
                start = time.perf_counter()
                ans = fn(context) or offline.generate(context)
                elapsed = time.perf_counter()-start
                then = time.perf_counter()
                validation = validate_answer(ans,context)
                signature,metrics = score(ans,r,corpus,cond,original.get(mode))
                if cond=='C1':
                    original[mode]=signature
                if mode=='dependency' and not validation.valid:
                    raise ValueError(validation.errors)
                review = time.perf_counter()-then
                results.append(dict(idx=i,kind=r['kind'],condition=cond,system=mode,question=r['question'],
                                    answer=ans.to_dict(),metrics=metrics,generation_s=elapsed,review_s=review))
                for metric,val in metrics.items():
                    key=(r['kind'],cond,metric)
                    buckets[(*key,mode)].append(val)
                    paired[(*key,i)][mode]=val
    dest = REPORT/args.split
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'answers.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in results))
    table = ['| Type | Condition | Metric | Baseline B (95% CI) | Dependency (95% CI) | Paired change (95% CI) | n |',
             '|---|---|---|---:|---:|---:|---:|']
    import numpy as np
    rng=np.random.default_rng(61113)
    for kind,cond,metric in sorted({k[:3] for k in buckets}):
        key=(kind,cond,metric)
        cells=[]
        for mode in ('baseline_B','dependency'):
            mean,lo,hi,n,_=interval(buckets[(*key,mode)])
            cells.append(f'{mean:.1%} [{lo:.1%}, {hi:.1%}]')
        diffs=[int(v['dependency'])-int(v['baseline_B']) if metric not in ('citation_precision','citation_recall') else float(v['dependency'])-float(v['baseline_B']) for k,v in paired.items() if k[:3]==key]
        sims=rng.choice(diffs,(10000,len(diffs))).mean(axis=1)
        lo,hi=np.quantile(sims,[.025,.975])
        table.append('| '+' | '.join([kind,cond,metric,*cells,f'{np.mean(diffs):+.1%} [{lo:+.1%}, {hi:+.1%}]',str(n)])+' |')
    (dest/'metrics.md').write_text('\n'.join(table)+'\n')
    timing = {s:{k:statistics.mean(r[k] for r in results if r['system']==s) for k in ['generation_s','review_s']} for s in ['dependency','baseline_B']}
    (dest/'timing.json').write_text(json.dumps(timing,indent=2)+'\n')
    print(len(results), 'answers:',dest)


if __name__=='__main__':
    main()
