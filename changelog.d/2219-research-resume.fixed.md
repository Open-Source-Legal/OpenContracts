- Preserve material findings across resumed deep-research workers (#2219).
  `ResearchReportService.finalize_once` recovers saved citation provenance;
  `ResearchReportService.finalize` rechecks current source access before retaining
  it in explicit or salvage reports.
