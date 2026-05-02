import React from "react";
import { useReactiveVar } from "@apollo/client";
import { MetaTags } from "../seo/MetaTags";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { ErrorBoundary } from "../widgets/ErrorBoundary";
import { openedExtract, routeLoading, routeError } from "../../graphql/cache";
import { ExtractDetail } from "../../views/ExtractDetail";

/**
 * ExtractDetailRoute - Renders the extract detail view for /extracts/:extractId
 * and /e/:userIdent/:extractIdent.
 *
 * URL parsing, GraphQL resolution, and reactive-var population are owned by
 * CentralRouteManager. This component reads the resolved state and renders.
 */
export const ExtractDetailRoute: React.FC = () => {
  const extract = useReactiveVar(openedExtract);
  const loading = useReactiveVar(routeLoading);
  const error = useReactiveVar(routeError);

  if (loading && !extract) {
    return <ModernLoadingDisplay type="extract" size="large" />;
  }

  if (error) {
    return (
      <ModernErrorDisplay
        type="extract"
        error={error.message || "Failed to load extract"}
      />
    );
  }

  if (!extract) {
    return <ModernErrorDisplay type="extract" error="Extract not found" />;
  }

  return (
    <ErrorBoundary>
      <MetaTags
        title={extract.name || "Extract"}
        description={`Extract: ${extract.name}`}
        entity={extract}
        entityType="extract"
      />
      <ExtractDetail />
    </ErrorBoundary>
  );
};

export default ExtractDetailRoute;
