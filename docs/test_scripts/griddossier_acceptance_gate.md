# Test: GridDossier acceptance gate — 100 MW Oncor readiness

## Purpose

Verify that a group-scoped deep-research run answers one fixed question well
enough to pass seven criteria. It exists because "the report looks good" is not
a claim anyone can check twice.

Everything below runs through **production surfaces only** — the
`startResearchReport` mutation, the corpus Research tab, the report page, and
the corpus chat agent. There is deliberately no evaluation command: a harness
that reaches inside the app measures the harness.

## The question

Fixed, and not to be edited casually — changing it silently changes what
passing means. It asks the agent to:

1. establish the governing ERCOT rule's effective date (and approval date if
   the record gives one) **before** recording any obligation;
2. record every requirement as an OBLIGATION finding card with `applicability`,
   `applies_at_mw` when phase-triggered, `responsible_party` plus any distinct
   preparer / submitter / recipient / certifier, and the right date in the
   right one of the six date fields;
3. walk the ramp in the report body, naming 25, 50, 75 and 100 MW in turn, and
   state a step where nothing attaches as an uncited absence finding — no
   passage entails a negative;
4. keep the ramp walk out of the cards: an absence has no responsible party.

The full text lives with the run in `ResearchReport.prompt`. Copy it from a
previous run's report page rather than re-typing it.

## Prerequisites

- Corpus `ercot-current-large-load-rules` (the anchor) and corpus group
  `dfw-large-load-public-authorities`, both visible to the operator.
- A real embedder configured in Pipeline Settings — **not** `TestEmbedder`,
  whose MD5 vectors make similarity search meaningless. See
  `docs/pipelines/pipeline_overview.md`.
- A model, set via the System Settings LLM picker (`PipelineSettings.default_llm`).
  The model is the largest single lever on this gate, so record which one a
  result came from. Measured: `gpt-4.1` reaches 4 of 7 criteria; `gpt-5.6-luna`
  reaches 6 of 7, with every deterministic criterion at 10/10. The difference is
  not subtle — `gpt-4.1` never once called `search_across_group` across
  twenty-one runs and so answered from the 2-document anchor corpus while 352
  documents sat in the group; `gpt-5.6-luna` uses it in every run.
  If you pick a GPT-5.6 model, read pitfall 20 in `CLAUDE.md` first — the family
  needs the Responses API for function tools, and the fixes are in-tree but the
  failure modes are worth recognising.
- Model credits. A ten-run pass is ~30 research runs' worth of model calls plus
  20 reviewer messages.
- The stack reads its key from `AUTHORITY_E2E_OPENAI_API_KEY` **at
  `docker compose up` time**. Bring the stack up without it exported and every
  run fails instantly with "Missing credentials" — cheap, but confusing.

## Steps

### 1. Launch a run from the GUI

Corpus → **Research** tab → **Start research**. Paste the question, and in
**Search a corpus group as well** pick *DFW Large-Load Public Authorities*.
Leaving it unset runs against the anchor corpus alone, which is a different
test.

The same thing scripted, for the ten-run pass (driving the platform, not
reimplementing it):

```graphql
mutation {
  startResearchReport(
    corpusId: "<relay id>"
    corpusGroupId: "<relay id>"
    prompt: "<the question>"
    title: "Acceptance gate: 100 MW Oncor readiness"
  ) { ok message obj { id slug status } }
}
```

Authenticate as in `CLAUDE.md` → *Authenticated Playwright Testing*. One run at
a time per (user, corpus): the service refuses a concurrent second by design.

### 2. Read the report page

The findings embed above the prose renders the obligation cards; the Run
details tab carries the tool-call log and the report's own warnings. Warnings
are the machine-checked half of this gate — most of what used to be scored
externally is now refused at `record_finding` or surfaced at finalize.

## Expected results

| # | Criterion | Where to look | Passes when |
|---|-----------|---------------|-------------|
| 1 | Applicability | Findings embed | Every card shows a class; a PHASE_TRIGGERED card names its ramp steps. Enforced at record time — a violation cannot reach the report. |
| 2 | Ramp analysis | Report body | 25, 50, 75 and 100 MW each named in the walk. A step stated as an absence carries no footnote. |
| 3 | Temporal analysis | Card date fields | More than one *kind* of date is used across the run, and no card gives the same value for approval and effective. |
| 4 | Evidence | Warnings | No "material obligation card(s) were withheld" warning, and every material card has a footnote. |
| 5 | Role accuracy | Card party fields | No card lacks an obligor (enforced at record time), and the run distinguishes preparer / submitter / recipient / certifier from the responsible party somewhere. |
| 6 | Expert validation | Corpus chat | See below. |
| 7 | Reliability | Ten runs | See below. |

### Criterion 6 — two reviewers, in the corpus chat

Open the corpus chat and review the report **twice, in two separate
conversations**, with the two lenses below. Separate conversations are the
point: two takes in one thread measure the thread.

**Each message must carry the cited passage TEXT, not just the report.** This
is the whole difference between a useful reviewer and an agreeable one — the
first version of this step showed the reviewers the report and the cards but
never the passages, so they could see that a sentence carried a footnote and
not what the footnote said, and both returned straight 5s including on
entailment, which they had no way to assess. Build the message as:

1. the report body and its findings cards (copy from the report page);
2. then, under a heading like `CITED PASSAGES`, one block per footnote —
   `annotation <id>: <the passage text>`. Read the ids off the Sources table at
   the foot of the report; the passage text is what the footnote links to. The
   agent can also fetch them itself, but pasting them is what was validated,
   and it removes any chance the reviewer scores entailment against a passage
   it retrieved instead of the one that was cited.

Scores come back as prose — read the six numbers off the reply. There is no
structured-output path here on purpose; a schema would be a second
implementation of the thing being tested.

- *The skeptical citation auditor.* "Your job is ENTAILMENT. For each footnote,
  read the quoted passage and ask whether it actually entails the sentence it
  supports, or is merely on the same topic. Topical relevance is NOT
  entailment. If a claim's passage does not contain the obligation it is cited
  for, citation_entailment is a 2 or lower."
- *The developer's counsel.* "Your job is OMISSION and PARTY ERROR. You advise
  the project. Ask what a competent adviser would notice is missing, and
  whether the party named on each obligation is the one who actually bears it —
  confusing the interconnecting entity with the utility is a serious defect."

Ask each for 1–5 on `precision`, `recall`, `party_accuracy`, `applicability`,
`temporal_accuracy`, `citation_entailment`, plus its worst problem, the
obligation it thinks is missing, and its weakest citation. **Both reviewers
must reach 4 on every dimension.**

**Hold the reviewers on one model across comparisons.** They are the measuring
instrument for this criterion; moving the author model and the judge together
makes the scores incomparable. Flip `default_llm` back to the baseline model and
restart the worker before reviewing. Tell them anything they cannot verify from
the supplied passages is at most a 3 — without that, and without the passage
text, the first version of this step returned straight 5s from both, which
measured the rubric's agreeableness and nothing else.

### Criterion 7 — ten runs

Repeat step 1 ten times and check across the runs:

- **No silent retrieval failure** — no run where every retrieval returned
  nothing and the report was written anyway.
- **No run cut off before finalize** — no report warning starting
  `terminal_reason:`. That warning names which budget ran out: the token
  budget, the *step* budget (`request_limit = max_steps`), or an agent that
  simply stopped. A cut-off run is salvage-composed and loses whatever body it
  had not written yet.
- **No missing audit log** — every report has a tool-call log.
- **No unsupported mandatory card**, **no empty run**.
- **Conclusions not materially inconsistent** — compare the *parties*, not
  their spellings. Ten runs produced 54 spellings of three parties (the
  interconnecting entity, the utility, ERCOT), and 31 of those strings name two
  parties at once. Judge which parties each run identified; agreement below
  half, or a card count varying more than threefold, is a real inconsistency.

Also worth reading per run, because it is what a failure usually is: **the tool
mix**. A run whose retrieval is all `find_citable_passages` never searched by
meaning and can only have found language it already guessed.

## Cleanup

Reports are durable by design — leave them. Each also writes a markdown copy to
the operator's workspace corpus under `Research Reports/`; delete those if the
corpus is being kept tidy.
