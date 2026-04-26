import React from "react";
import { useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { MetaTags } from "../seo/MetaTags";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { ErrorBoundary } from "../widgets/ErrorBoundary";
import { openedLabelset, routeLoading, routeError } from "../../graphql/cache";
import { LabelSetDetailPage } from "../labelsets/LabelSetDetailPage";

/**
 * LabelSetLandingRoute - Handles labelset routes with /label_sets/:id pattern
 *
 * Route pattern:
 * - /label_sets/:labelsetId (ID-based, labelsets don't have slugs)
 *
 * This component is a DUMB CONSUMER - it just reads state set by CentralRouteManager.
 * It displays the LabelSetDetailPage for a full-page experience.
 */
export const LabelSetLandingRoute: React.FC = () => {
  const navigate = useNavigate();

  // Read state from reactive vars (set by CentralRouteManager)
  const labelset = useReactiveVar(openedLabelset);
  const loading = useReactiveVar(routeLoading);
  const error = useReactiveVar(routeError);

  console.log("[LabelSetLandingRoute] 🔄 Render triggered", {
    hasLabelset: !!labelset,
    loading,
    hasError: !!error,
  });

  // Handle close by navigating back to list. CentralRouteManager Phase 1
  // clears openedLabelset when the new path resolves to a browse route.
  const handleClose = () => {
    navigate("/label_sets");
  };

  if (loading) {
    return <ModernLoadingDisplay type="default" size="large" />;
  }

  if (error || !labelset) {
    return (
      <ModernErrorDisplay
        type="generic"
        error={error || "Label set not found"}
      />
    );
  }

  return (
    <ErrorBoundary>
      <MetaTags
        title={labelset.title || "Label Set"}
        description={labelset.description || `Label Set: ${labelset.title}`}
      />
      <LabelSetDetailPage onClose={handleClose} />
    </ErrorBoundary>
  );
};

export default LabelSetLandingRoute;
