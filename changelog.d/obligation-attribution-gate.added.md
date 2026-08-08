- Obligation finding cards now have an attribution gate: a material card whose
  cited passages never name its `responsible_party` is refused at
  `record_finding` with an actionable message, rather than reaching the report
  (`opencontractserver/tasks/research_tasks.py::_build_obligation_card`, backed
  by `research/services/research_reports.py::party_named_in_passages`). This is
  the defect two adversarial reviewers found independently on the same report,
  from opposite directions — "the passage supports the $50,000/MW figure but
  does not itself specify who must post it" and "duties the ILLE bears are at
  times assigned to the TSP". Both are one failure, and it survives every other
  check: the obligation is real, the citation is real, and only the obligor is
  imported from somewhere else. Word-overlap over the claim cannot see it,
  because the claim scores fine on everything except the one word that matters.
  Acronyms are matched alongside content words, so a defined term (`TSP`,
  `ILLE`) below the length floor still grounds a card. `cited_passages` is a
  required parameter of `_build_finding_card` on purpose — a default would let
  a caller skip the gate by forgetting an argument.
