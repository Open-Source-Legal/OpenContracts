import React from "react";
import { useReactiveVar } from "@apollo/client";
import { MetaTags } from "../seo/MetaTags";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { ErrorBoundary } from "../widgets/ErrorBoundary";
import { openedResearchReport, routeLoading } from "../../graphql/cache";
import { ResearchReportDetail } from "../../views/ResearchReportDetail";

/**
 * ResearchReportRoute - Renders the deep-research report detail view for
 * /research/:slug (the URL the backend completion chat message links to).
 *
 * URL parsing, GraphQL slug resolution, and reactive-var population are owned
 * by CentralRouteManager. This component reads the resolved state and renders.
 * Reports are creator-only (v1): a non-owner resolves to null → "not found".
 */
export const ResearchReportRoute: React.FC = () => {
  const report = useReactiveVar(openedResearchReport);
  const loading = useReactiveVar(routeLoading);

  if (loading && !report) {
    return (
      <ModernLoadingDisplay
        type="default"
        size="large"
        message="Loading research report…"
      />
    );
  }

  // CentralRouteManager redirects to /404 on GraphQL error or null data, so
  // the only state that reaches here without a report is the not-found case.
  if (!report) {
    return (
      <ModernErrorDisplay
        type="generic"
        title="Research report not found"
        error="This research report doesn't exist or you don't have access to it."
      />
    );
  }

  return (
    <ErrorBoundary>
      <MetaTags
        title={report.title || "Research Report"}
        description={`Deep research report: ${report.title}`}
      />
      <ResearchReportDetail />
    </ErrorBoundary>
  );
};

export default ResearchReportRoute;
