- Deep research: across twenty runs of a group-scoped question the agent called
  `search_across_group` **zero** times. It searched the anchor corpus, got
  hits, and stopped — which was reasonable, because nothing told it the anchor
  held 2 documents out of the group's 354, or that the utility corpus the
  question is about was one of the nine it never opened. Knowing the tool
  existed was not enough. The mission prompt now states the group's shape —
  corpus count, total documents, and how many the anchor holds — counted
  through `CorpusGroupService.get_group_corpora_visible_to_user` with the
  report creator's permissions so it never advertises a corpus the caller
  cannot read (`research_tasks.py::_describe_group_scale`,
  `research/constants.py::build_deep_research_system_prompt`). The tool's own
  description was also rebalanced: it opened with two sentences of cost warning
  about `k`, which is a good way to make a model avoid a tool entirely.
