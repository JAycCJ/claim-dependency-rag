"""Score hosted responses with the unchanged phase-six rubric, keeping service errors separate."""
import csv
import random
import json
from collections import Counter, defaultdict
from statistics import mean, median
from evaluate_dependencies import OUT, REPORT, interval, records, score
from generation.schema import Claim, GeneratedAnswer
import numpy as np


def write_report():
    dest = REPORT/'fenno_frozen_50'
    rows = list(map(json.loads,(dest/'answers.jsonl').read_text().splitlines()))
    assert len(rows)==len({(r['idx'],r['condition']) for r in rows})
    questions = list(map(json.loads,(OUT/'evaluation.jsonl').read_text().splitlines()))
    ids = {cid for r in rows for cid in (*questions[r['idx']]['ids'],questions[r['idx']]['distractor'])}
    corpus = {p['chunk_id']:p for p in records() if p['chunk_id'] in ids}
    references = {(r['idx'],r['condition']):r for r in map(json.loads,(REPORT/'evaluation/answers.jsonl').read_text().splitlines()) if r['system']=='dependency'}
    cases = []
    pairs = defaultdict(list)
    original = {}
    for r in rows:
        q=questions[r['idx']]
        row = {k:r[k] for k in ('idx','kind','condition','generation_s')}
        row.update(question=q['question'],error=r.get('error'),http_status=r.get('http_status'))
        if 'answer' in r:
            data = r['answer']
            answer=GeneratedAnswer(**{**data,'claims':[Claim(**c) for c in data['claims']]})
            sig,metrics=score(answer,q,corpus,r['condition'],original.get(r['idx']))
            if r['condition']=='C1':
                original[r['idx']]=sig
            ref=references[r['idx'],r['condition']]['metrics']
            for name,value in metrics.items():
                pairs[r['kind'],r['condition'],name].append((value,ref[name]))
            row.update(status=answer.status,answer=answer.answer,limitations=answer.limitations,metrics=metrics,
                       validation=r['validation'],reference_metrics=ref)
        cases.append(row)
    (dest/'scores.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in cases))
    # Hand off a reproducible blinded sheet; a human reviewer supplies the labels.
    eligible=[r for r in cases if 'answer' in r]
    if len(eligible)>=30:
        rng_review=random.Random(61113)
        selected=rng_review.sample(eligible,30)
        with (dest/'review_30.csv').open('w',newline='') as stream:
            w=csv.writer(stream)
            w.writerow(['idx','condition','question','answer','limitations','human_asserted_comparison','reviewer','notes'])
            for r in selected:
                w.writerow([r['idx'],r['condition'],r['question'],r['answer'],json.dumps(r['limitations']),'','',''])
    summary=['# Fenno 冻结集对照','',f'共 {len(rows)} 次请求，涉及 {len(set(r["idx"] for r in rows))} 道独立问题。']
    table=['','| 条件 | 请求 | 结构化返回 | 通过现有校验 | 拒答 | HTTP 429 |','|---|---:|---:|---:|---:|---:|']
    for condition in ['C1','C2','C3','C4']:
        part=[r for r in cases if r['condition']==condition]
        table.append(f'| {condition} | {len(part)} | {sum("answer" in r for r in part)} | {sum(r.get("validation")==[] for r in part)} | {sum(r.get("status")=="refuse" for r in part)} | {sum(r["http_status"]==429 for r in part)} |')
    summary+=table
    success=[r for r in rows if 'answer' in r]
    if success:
        summary+=['',f'成功返回的生成延迟均值 {mean(r["generation_s"] for r in success):.2f} 秒，中位数 {median(r["generation_s"] for r in success):.2f} 秒。平均确定性校验时间 {mean(r["review_s"] for r in success):.6f} 秒。']
    usage=Counter()
    for r in success:
        for k in ('input_tokens','output_tokens'):
            usage[k]+=r['answer']['diagnostics']['usage'].get(k) or 0
    summary += ['',f'成功返回的 token 用量：输入 {usage["input_tokens"]:,}、输出 {usage["output_tokens"]:,}。失败请求用量和实际账单未知。','',
        '以下为原有固定规则评分。分母仅含该条件返回结构化回答的题；网络错误只计入上表。每行两种系统在同一组题上配对。英文自由文本中的同义词、反向叙述和分句可能漏判，因此不能把规则分数当人工准确率。恢复一致率要求比较文字和引用复现，措辞变化也会失分。',
        '', '| 题型 | 条件 | 指标 | n | Fenno [95% CI] | 依赖系统 [95% CI] | 差异及配对 bootstrap 95% CI（百分点） |','|---|---|---|---:|---:|---:|---:|']
    rng=np.random.default_rng(61113)
    for (kind,cond,k),data in sorted(pairs.items()):
        a,b=zip(*data)
        def cell(v):
            val,lo,hi,*_=interval(list(v))
            return f'{val:.1%} [{lo:.1%}, {hi:.1%}]'
        delta=np.array(b,dtype=float)-np.array(a,dtype=float)
        lo,hi=np.quantile(rng.choice(delta,(10000,len(delta))).mean(axis=1),[.025,.975])*100
        summary.append(f'| {kind} | {cond} | {k} | {len(a)} | {cell(a)} | {cell(b)} | {delta.mean()*100:+.1f} [{lo:+.1f}, {hi:+.1f}] |')
    (dest/'metrics.md').write_text('\n'.join(summary)+'\n')


if __name__=='__main__':
    write_report()
