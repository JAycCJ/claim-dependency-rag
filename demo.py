"""Demonstrate removal and restoration with invented records. No external services."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent/'src'))
from augmentation.schema import ContextPackage, EvidencePassage
from generation.dependencies import generate_comparison, retract
from generation.validator import validate_answer

QUESTION = 'Compare enrichment_beta for 2hrG, annotation demo, tissue demo, biosample demo, between EA and EU.'
COLLECTION = 'ldsc_partitioned_heritability'


def context(labels):
    passages = []
    for label in labels:
        cid = f'ldsc_partitioned:2hrG:demo:demo:demo:{label}'
        value = {'EA': 4, 'EU': 7, 'HS': 19}[label]
        passages.append(EvidencePassage(cid, COLLECTION, len(passages)+1, 1, label,
            'Synthetic record', {'enrichment_beta': value}, {'chunk_id': cid}))
    return ContextPackage(QUESTION,[COLLECTION],[COLLECTION],'synthetic',passages,
        {p.chunk_id:p.citation for p in passages},'answer',[],0,1800)


def main():
    original = generate_comparison(context(['EA','EU']))
    for name,labels in [('Complete',['EA','EU']),('Withdraw EU',['EA']),
                        ('Add unrelated HS',['EA','HS']),('Restore EU',['EU','EA'])]:
        ctx=context(labels)
        answer=retract(original,ctx)
        assert validate_answer(answer,ctx).valid
        print(name, answer.answer, *answer.limitations, sep='\n', end='\n\n')
        if 'EU' not in labels:
            assert len(answer.claims)==1 and answer.status=='qualified'
        else:
            assert answer.claims==original.claims


if __name__=='__main__':
    main()
