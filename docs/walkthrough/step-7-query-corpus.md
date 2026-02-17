# Querying a Corpus

Once you've created a corpus of documents, you can use the **Corpus Chat** feature to ask natural language questions
and get AI-powered answers, complete with citations and links back to the relevant text in the document(s).

The chat interface maintains conversation history, allowing you to ask follow-up questions and explore your documents
interactively.

![Corpus Query.gif](../assets/images/gifs/Corpus_Query.gif)

## Understanding Tool Usage

When the AI agent answers your questions, it uses various tools behind the scenes — searching for similar text,
performing exact text lookups, or querying specific documents. You can see exactly what the agent did by looking
at the **tool usage badge** that appears next to the assistant's name.

![Tool Usage Badge](../assets/images/screenshots/auto/chat--tool-badge--single.png)

Hover over (or click) the badge to open a popover showing each tool call with its input arguments and output:

![Single Tool Popover](../assets/images/screenshots/auto/chat--tool-popover--single-tool.png)

For complex queries, the agent may chain multiple tools together. The popover lists all calls in execution order:

![Multi-Tool Popover](../assets/images/screenshots/auto/chat--tool-popover--multi-tool.png)

The full set of tools available to agents is defined in
[`opencontractserver/llms/tools/core_tools.py`](https://github.com/Open-Source-Legal/OpenContracts/blob/main/opencontractserver/llms/tools/core_tools.py).
