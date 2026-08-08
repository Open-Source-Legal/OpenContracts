- OpenAI's GPT-5.6 family (Sol / Terra / Luna) is now selectable and works.
  Registered in `OpenAIProvider.supported_models` with a 1M context window in
  `constants/context_guardrails.py` — the window is explicit for the same
  reason every `gpt-4.*` entry is, since an unlisted name falls to the 128K
  default and would size a 1M-window model at an eighth of its budget, moving
  when a deep-research run compacts. These models also reject function tools on
  `/v1/chat/completions` whenever `reasoning_effort` is set, so
  `model_factory.requires_responses_api` routes them to `/v1/responses`
  automatically, on both the DB-credential and env-credential paths. Automatic
  rather than operator-configured: the names appear in the System Settings LLM
  picker, and choosing one would otherwise 400 every agent in the install with
  an explanation visible only in a worker log.
- Deep research: `terminal_reason` clamped provider errors at 200 characters,
  which cut OpenAI's 400 mid-sentence and dropped the half that mattered —
  "…not supported for gpt-5.6-luna in /v1/chat/completions. To use function
  tools," stopped exactly before the remedy. Raised to 600.
