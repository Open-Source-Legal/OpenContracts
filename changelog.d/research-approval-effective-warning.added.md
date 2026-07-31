- A research report now warns when a finding card gives the same date for
  approval and effectiveness (`ResearchReportService.finalize`). A regulator
  approving an instrument is a different event from the instrument taking
  effect, and the gap between them is exactly the window a reader needs when
  asking which regime governed a given day — the card keeps the two in separate
  fields so a conflation is visible. Flagged rather than refused: the two
  genuinely coincide often enough that blocking the card would be wrong.
