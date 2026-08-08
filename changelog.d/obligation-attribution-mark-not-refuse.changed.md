- The obligation-card attribution check now MARKS instead of refusing. A card
  whose cited passages never name its `responsible_party` is kept, with
  `obligor_grounded: false`, and the report warns how many attributions are
  inferred rather than sourced
  (`opencontractserver/enrichment/finding_cards.py`,
  `research_tasks.py::_build_obligation_card`,
  `research/services/research_reports.py::finalize`). Refusing cost more than
  it bought: a run that found many requirements filed **two**, because every
  refusal deletes the obligation along with the bad attribution. Worse, the
  refusal offered a way out in prose, and the agent spent its remaining budget
  guessing at it — `responsible_party="Not specified in cited passage"`, then
  the text of the instruction itself pasted in as a party name. No wording of a
  refusal makes a passage name a party it does not name. An obligation with an
  inferred obligor is worth recording and worth labelling; it is not worth
  deleting.
