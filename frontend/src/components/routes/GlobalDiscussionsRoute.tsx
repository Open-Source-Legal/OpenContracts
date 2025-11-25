import React from "react";
import { ErrorBoundary } from "../widgets/ErrorBoundary";
import { MetaTags } from "../seo/MetaTags";
import { GlobalDiscussions } from "../../views/GlobalDiscussions";

/**
 * Route wrapper for global discussions view.
 * Shows all platform discussions with tabbed filtering.
 *
 * Part of Issue #623 - Global Discussions Forum View
 */
export const GlobalDiscussionsRoute: React.FC = () => {
  return (
    <ErrorBoundary>
      <MetaTags
        title="Discussions - OpenContracts"
        description="Browse all platform discussions"
      />
      <GlobalDiscussions />
    </ErrorBoundary>
  );
};
