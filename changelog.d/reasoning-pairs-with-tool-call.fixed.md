- In-run history compaction dropped `ThinkingPart`s from responses that also
  carried a `ToolCallPart`. OpenAI's Responses API treats the two as one unit
  and rejects the request outright — *"Item 'fc_…' of type 'function_call' was
  provided without its required 'reasoning' item: 'rs_…'"* — so a deep-research
  run on a GPT-5.6 model died with a 400 after 38 tool calls and nothing
  recorded. Chat Completions tolerates the split, which is why this stayed
  invisible until the endpoint moved.
  `llms/history_processors.py::_shrink_message` now keeps reasoning on any
  response that called a tool. Written as an invariant rather than a
  per-provider switch: reasoning that produced a tool call is part of that
  call's record, and dropping half a pair is not a saving. Reasoning-only
  responses still shed their thinking, which is where most of the context
  saving was. Two pre-existing tests changed fixtures — every response
  `_make_pair` builds carries a tool call, so the drop is now demonstrated on a
  reasoning-only response; their original intent (older thinking goes, recent
  thinking stays) is unchanged.
