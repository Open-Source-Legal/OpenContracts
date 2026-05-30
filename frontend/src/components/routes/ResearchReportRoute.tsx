import React from "react";
import { useReactiveVar } from "@apollo/client";
import { MetaTags } from "../seo/MetaTags";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { ErrorBoundary } from "../widgets/ErrorBoundary";
import {
  openedResearchReport,
  routeLoading,
  routeError,
} from "../../graphql/cache";
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
  const error = useReactiveVar(routeError);

  if (loading && !report) {
    return (
      <ModernLoadingDisplay
        type="default"
        size="large"
        message="Loading research report…"
      />
    );
  }

  if (error) {
    return (
      <ModernErrorDisplay
        type="generic"
        title="Research report"
        error={error.message || "Failed to load research report"}
      />
    );
  }

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
