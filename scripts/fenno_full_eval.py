"""Frozen, proportional stratified sample. Journal before transmission; no retries."""
import json
import random
import time
from pathlib import Path
from evaluate_dependencies import OUT, digest, fixed_context, records
from generation.validator import validate_answer


def sample():
    path = OUT / 'evaluation.jsonl'
    manifest = json.loads((OUT/'manifest.json').read_text())
    if digest(path) != manifest['splits']['evaluation']['sha256']:
        raise ValueError('Frozen dataset hash mismatch')
    rows = list(map(json.loads,path.read_text().splitlines()))
    rng = random.Random(61113)
    selected = []
    for kind, count in [('ldsc',42), ('wes',8)]:
        selected.extend(rng.sample([(i,r) for i,r in enumerate(rows) if r['kind']==kind], count))
    rng.shuffle(selected)
    return selected


def run_full(gen, dest):
    selected = sample()
    ids = {cid for _,r in selected for cid in [*r['ids'],r['distractor']]}
    corpus = {r['chunk_id']:r for r in records() if r['chunk_id'] in ids}
    dest.mkdir(exist_ok=True,parents=True)
    with (dest/'attempts.jsonl').open('x') as attempts, (dest/'answers.jsonl').open('x') as answers:
        for idx,r in selected:
            a,b = r['ids']
            for cond,evidence in [('C1',[a,b]),('C2',[a]),('C3',[a,r['distractor']]),('C4',[b,a])]:
                ctx = fixed_context(r['question'],evidence,corpus)
                item = dict(idx=idx,kind=r['kind'],condition=cond)
                attempts.write(json.dumps(item)+'\n')
                attempts.flush()
                start = time.monotonic()
                try:
                    answer = gen.generate(ctx)
                    item['generation_s'] = time.monotonic()-start
                    t = time.monotonic()
                    item.update(answer=answer.to_dict(),validation=validate_answer(answer,ctx).errors, review_s=time.monotonic()-t)
                except Exception as exc:
                    cause = exc.__cause__ or exc
                    item.update(error=type(exc).__name__, cause=type(cause).__name__,http_status=getattr(cause,'status_code',None),generation_s=time.monotonic()-start)
                answers.write(json.dumps(item)+'\n')
                answers.flush()
                if item.get('http_status') in (401,403,402):
                    return 'Stopped: upstream authentication or billing error.'
                if item.get('http_status')==429:
                    time.sleep(15)
    return 'Completed 200 conditions.'
