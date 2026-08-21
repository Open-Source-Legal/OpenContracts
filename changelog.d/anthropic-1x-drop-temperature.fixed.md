- **`anthropic` 1.0.0 removed the sampling parameters, breaking both direct
  `messages.create()` calls.** `temperature` is gone from the SDK's runtime
  signature and from all three `create()` overloads, and there is no `**kwargs`
  passthrough — so `temperature=0` now raises
  `TypeError: Messages.create() got an unexpected keyword argument
  'temperature'` **before the request is built**. That is a hard crash, not an
  API-level 400. It reached `main` with no commit touching the code:
  `requirements/analyzers/claude_highlighter.txt` declares `anthropic>=0.45.2`
  with **no upper bound**, both Dockerfiles glob every
  `requirements/*/*.txt` into the image, and there is no lock file — so a
  major release published upstream is picked up by the next resolve, in CI
  and in the production image alike. Both call sites in
  `doc_analysis_tasks.py` (chunked text extraction and the Claude PII scanner)
  drop the parameter. The API removed `temperature` on Opus 4.7+ and rejects
  it on Sonnet 5, so this is the forward-correct fix rather than a
  client-only shim; determinism, where it matters, comes from the prompt, and
  `temperature=0` never guaranteed identical outputs in any case. The
  `temperature=0` guard in the pydantic-ai layer (issue #1381) is a different
  code path and is unaffected.
- **Pinned `anthropic` to `>=0.45.2,<1` as a stopgap, in both the analyzer
  requirements and the mypy hook's `additional_dependencies`.** Note the
  ceiling is `<1`, not `<2` — `1.0.0` satisfies `<2`, so that bound would be a
  no-op (verified: `>=0.45.2` and `>=0.45.2,<2` both resolve to `1.0.0`;
  `>=0.45.2,<1` resolves to `0.125.0`). Mirroring the pin into the pre-commit
  hook matters because that hook resolves its own dependency set — without it
  CI type-checks against a different major than the image ships, which is how
  this broke `main` with no commit touching the code. Migration onto the 1.x
  line is tracked in #2273.
