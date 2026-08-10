#!/usr/bin/env python3
"""Run the Fort Worth homeowner gold questions against the live corpus agent.

Runs inside the django container:
    python manage.py shell < run_gold_questions.py

Each question records the answer plus the authority keys the agent actually
cited, so a reviewer can check the citation, not just the prose.
"""
import asyncio
import json
import os
import re

CORPUS_ID = 123
# Per-call override; falls back to the install default (OPENAI_MODEL) when unset.
MODEL = os.environ.get("GOLD_MODEL") or None
RESULTS_PATH = os.environ.get("GOLD_OUT", "/tmp/gold_results.json")

QUESTIONS = [
    ("Q1-water-heater",
     "I want to replace my water heater myself. Do I need a permit, and am I "
     "allowed to do the work myself?"),
    ("Q2-fence-height",
     "How tall can I build a fence at my house, and do I need a permit for it?"),
    ("Q3-own-electrical",
     "Can I do my own electrical work in the house I own and live in?"),
    ("Q4-drywall",
     "Do I need a permit to replace drywall in a bedroom?"),
    ("Q5-reroof",
     "Do I need a permit to re-roof my house?"),
    ("Q6-shed",
     "Can I put up a storage shed in my back yard without a permit?"),
    ("Q7-contractor-registration",
     "Do I have to hire a registered contractor, or can I pull the permit "
     "myself as the homeowner?"),
    ("Q8-inspections",
     "What inspections will my project need, and how do I schedule them?"),
    ("Q9-hoa-solar",
     "My HOA says I cannot install solar panels. Can they stop me?"),
    ("Q10-code-editions",
     "Which editions of the building codes has Fort Worth actually adopted?"),
]

KEY_RE = re.compile(
    r"\b(fw-admin-code|fw-res-code|fw-zoning|muni-fort-worth|tx-occ|tx-prop|"
    r"fw-charter|tx-local-gov|tx-gov):[A-Za-z0-9.\-()]+"
)
# Human citation forms the personas actually ask for.
CITE_RE = re.compile(
    r"(Building Administrative Code\s*§*\s*\d+(?:\.\d+)*"
    r"|Zoning Ordinance\s*§*\s*\d+\.\d+"
    r"|Occupations Code\s*§*\s*\d+\.\d+"
    r"|Property Code\s*§*\s*\d+\.\d+"
    r"|City Code\s*§*\s*\d+-\d+"
    r"|IRC\s+[A-Z]?\d+(?:\.\d+)*)",
    re.I,
)


async def main() -> None:
    from opencontractserver.llms import agents

    results = []
    for qid, question in QUESTIONS:
        print(f"\n{'='*78}\n{qid}: {question}\n{'='*78}", flush=True)
        try:
            kwargs = {"model": MODEL} if MODEL else {}
            agent = await agents.for_corpus(
                corpus=CORPUS_ID, user_id=1, streaming=False, persist=False, **kwargs
            )
            resp = await agent.chat(question)
            answer = getattr(resp, "content", None) or str(resp)
        except Exception as exc:  # surface, never swallow
            answer = f"ERROR: {type(exc).__name__}: {exc}"
        print(answer, flush=True)
        results.append({
            "id": qid,
            "question": question,
            "answer": answer,
            "keys_cited": sorted(set(KEY_RE.findall(answer))),
            "citations": sorted(set(m.group(0) for m in CITE_RE.finditer(answer))),
        })

    with open(RESULTS_PATH, "w") as fh:
        json.dump(results, fh, indent=2)

    print(f"\n\n{'#'*78}\nSUMMARY (model={MODEL or 'install default'})\n{'#'*78}")
    for r in results:
        status = "ERR " if r["answer"].startswith("ERROR:") else "ok  "
        print(f"{status}{r['id']:28} cites={len(r['citations']):>2} "
              f"keys={len(r['keys_cited'])}")


asyncio.run(main())
