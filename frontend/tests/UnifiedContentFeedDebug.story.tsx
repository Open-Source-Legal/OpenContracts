import React from "react";
import { UnifiedContentFeedTestWrapper } from "./UnifiedContentFeedTestWrapper";
import { ContentFilters } from "../src/components/knowledge_base/document/unified_feed/types";

// Debug component to log atom values
export const DebugAtoms = () => {
  const {
    useVisibleAnnotations,
  } = require("../src/components/annotator/hooks/useVisibleAnnotations");
  const {
    usePdfAnnotations,
  } = require("../src/components/annotator/hooks/AnnotationHooks");
  const {
    useAllAnnotations,
  } = require("../src/components/annotator/hooks/useAllAnnotations");
  const {
    useAnnotationDisplay,
  } = require("../src/components/annotator/context/UISettingsAtom");

  const visibleAnnotations = useVisibleAnnotations();
  const { pdfAnnotations } = usePdfAnnotations();
  const allAnnotations = useAllAnnotations();
  const { showStructural } = useAnnotationDisplay();

  React.useEffect(() => {
    console.log("DEBUG - visibleAnnotations:", visibleAnnotations);
    console.log("DEBUG - pdfAnnotations:", pdfAnnotations);
    console.log("DEBUG - allAnnotations:", allAnnotations);
    console.log("DEBUG - showStructural:", showStructural);
  }, [visibleAnnotations, pdfAnnotations, allAnnotations, showStructural]);

  return null;
};

// Story combining wrapper with debug atoms
export const UnifiedContentFeedWithDebugAtoms = ({
  notes = [],
  mockAnnotations = [],
}: {
  notes?: any[];
  mockAnnotations?: any[];
}) => {
  return (
    <>
      <UnifiedContentFeedTestWrapper
        notes={notes}
        mockAnnotations={mockAnnotations}
      />
      <DebugAtoms />
    </>
  );
};

// Debug component for filter timing
export const TestComponentWithRenderTracking = () => {
  const [renderCount, setRenderCount] = React.useState(0);

  const [notes] = React.useState([
    {
      id: "1",
      title: "Test Note 1",
      content: "This is the first test note",
      created: new Date().toISOString(),
      creator: { email: "test@example.com" },
    },
  ]);

  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setRenderCount((prev) => {
      const newCount = prev + 1;
      console.log(`DEBUG - Render #${newCount}, mounted: ${mounted}`);
      return newCount;
    });
    setMounted(true);
  }, [mounted]);

  return (
    <>
      <UnifiedContentFeedTestWrapper
        notes={notes}
        filters={{
          contentTypes: new Set(["note"]),
          annotationFilters: { showStructural: false },
          relationshipFilters: { showStructural: false },
          searchQuery: "",
        }}
      />
      <div data-testid="render-count" style={{ display: "none" }}>
        {renderCount}
      </div>
    </>
  );
};

// Debug component that logs filter state
export const DebugFilters = ({ filters }: { filters: any }) => {
  React.useEffect(() => {
    console.log("DEBUG - Filters passed to component:", filters);
    console.log("DEBUG - contentTypes Set:", Array.from(filters.contentTypes));
  }, [filters]);
  return null;
};

// Story combining wrapper with filter debugger
export const UnifiedContentFeedWithDebugFilters = ({
  notes = [],
  filters,
}: {
  notes?: any[];
  filters: ContentFilters;
}) => {
  // Log filters at story level
  React.useEffect(() => {
    console.log("Story level - filters:", filters);
    console.log("Story level - contentTypes:", filters.contentTypes);
    console.log(
      "Story level - contentTypes is Set?",
      filters.contentTypes instanceof Set
    );
  }, [filters]);

  return (
    <>
      <UnifiedContentFeedTestWrapper notes={notes} filters={filters} />
      <DebugFilters filters={filters} />
    </>
  );
};

// Debug component to log what filters it receives
export const DebugComponentForFilters = ({ filters }: { filters: any }) => {
  React.useEffect(() => {
    console.log("Filters received:", filters);
    console.log("contentTypes type:", typeof filters.contentTypes);
    console.log("contentTypes value:", filters.contentTypes);
    console.log("Is Set?", filters.contentTypes instanceof Set);
    console.log("Is Array?", Array.isArray(filters.contentTypes));
  }, [filters]);

  return <div>Debug Component</div>;
};
