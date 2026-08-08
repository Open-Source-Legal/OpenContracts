- Deep research: the mission prompt told the agent to DISCOVER by meaning and
  then PIN the exact language with `find_citable_passages`. That is two
  retrievals per finding, and it halved the card yield — across ten runs the
  agent spent up to 42 calls on phrase lookups (which were *hitting*, not
  missing) and filed two or three cards before its step budget ran down, where
  the run that made only four phrase calls filed seven. The prompt now says
  what is actually true: every search hit carries its `annotation_id`, which IS
  the cite handle, so no second lookup is needed to cite it, and
  `find_citable_passages` is for when you know the exact words and search has
  not surfaced them (`research/constants.py::build_deep_research_system_prompt`).
