import React from "react";
import { useNavigate } from "react-router-dom";
import { CollectionCard } from "@os-legal/ui";
import { JobStatus, ResearchReportListItem } from "../../types/graphql-api";
import {
  getResearchStatus,
  formatResearchDate,
  formatResearchDuration,
} from "../../utils/researchUtils";
import { getResearchReportUrl } from "../../utils/navigationUtils";

interface ResearchReportListCardProps {
  report: ResearchReportListItem;
}

/**
 * List card for a deep-research report. Clicking navigates to the standalone
 * /research/:slug detail page (reports are read-only and self-contained, so —
 * unlike Extracts — there's no inline split-view editing to justify).
 */
export const ResearchReportListCard: React.FC<ResearchReportListCardProps> = ({
  report,
}) => {
  const navigate = useNavigate();

  const statusLabel = getResearchStatus(report.status).label;
  const description = report.created
    ? `Created ${formatResearchDate(report.created)}`
    : "";

  const stats: string[] = [];
  if (
    report.status === JobStatus.Running ||
    report.status === JobStatus.Queued
  ) {
    stats.push(`Step ${report.stepCount ?? 0} of ${report.maxSteps ?? "—"}`);
  } else {
    const duration = formatResearchDuration(report.durationSeconds);
    if (duration) stats.push(`Ran ${duration}`);
  }

  const handleClick = () => {
    const url = getResearchReportUrl(report);
    if (url !== "#") {
      navigate(url);
    } else {
      // The list query always returns a slug, so a sentinel URL here means an
      // unexpected data shape — surface it rather than silently no-op.
      console.warn(
        "[ResearchReportListCard] Missing slug for report; cannot navigate",
        report?.id
      );
    }
  };

  return (
    <CollectionCard
      type="default"
      status={statusLabel}
      title={report.title || "Untitled Research"}
      description={description}
      stats={stats}
      onClick={handleClick}
      role="article"
      aria-label={`Research report: ${report.title || "Untitled Research"}`}
    />
  );
};

export default ResearchReportListCard;
