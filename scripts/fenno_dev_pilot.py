"""Two development questions, eight paired evidence conditions; no automatic retries."""
import json
import time
from pathlib import Path

from evaluate_dependencies import OUT, REPORT, digest, fixed_context, records
from generation.dependencies import generate_comparison
from generation.validator import validate_answer


def run_pilot(generator, directory, single=False):
    dev = OUT / "dev.jsonl"
    expected = json.loads((OUT / "manifest.json").read_text())["splits"]["dev"]["sha256"]
    if digest(dev) != expected:
        raise ValueError("Development data hash mismatch")
    questions = [json.loads(line) for line in dev.read_text().splitlines()]
    examples = [next(q for q in questions if q["kind"] == kind) for kind in ("ldsc", "wes")]
    ids = {cid for q in examples for cid in [*q["ids"], q["distractor"]]}
    corpus = {r["chunk_id"]: r for r in records() if r["chunk_id"] in ids}
    path = directory / "pilot.jsonl"
    directory.mkdir(parents=True, exist_ok=True)
    succeeded = 0
    with path.open("x") as output:
        for question in examples:
            a, b = question["ids"]
            for condition, evidence in (("C1",[a,b]),("C2",[a]),("C3",[a,question["distractor"]]),("C4",[b,a])):
                if single and (question["kind"], condition) != ("ldsc", "C4"):
                    continue
                ctx = fixed_context(question["question"], evidence, corpus)
                reference = generate_comparison(ctx)
                row = dict(kind=question["kind"], condition=condition, question=ctx.question,
                           evidence=evidence, reference=reference.to_dict(), model=generator.model)
                start = time.monotonic()
                try:
                    answer = generator.generate(ctx)
                    row["generation_s"] = time.monotonic()-start
                    start_review = time.monotonic()
                    validation = validate_answer(answer,ctx)
                    row.update(answer=answer.to_dict(), validation=validation.errors,
                               review_s=time.monotonic()-start_review)
                    succeeded += 1
                except Exception as exc:
                    cause = exc.__cause__ or exc
                    status = getattr(cause, "status_code", None)
                    row.update(error=type(exc).__name__, cause_type=type(cause).__name__,
                               http_status=status if type(status) is int else None,
                               generation_s=time.monotonic()-start)
                output.write(json.dumps(row, ensure_ascii=False)+"\n")
                output.flush()
    return succeeded
