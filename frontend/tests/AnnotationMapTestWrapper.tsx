import React from "react";
import { MemoryRouter } from "react-router-dom";
import { AnnotationMap } from "../src/components/maps/AnnotationMap";
import type { AnnotationMapProps } from "../src/components/maps/types";

/**
 * Test wrapper for {@link AnnotationMap}.
 *
 * AnnotationMap uses `useNavigate` for document deep-links, so it must be
 * mounted under a Router. No Apollo provider is needed — the component takes
 * pins as a prop and performs no queries of its own.
 *
 * Per CLAUDE.md pitfall #16, the `.ct.tsx` file imports THIS wrapper component
 * in its own import statement, separate from helper/fixture imports.
 */
export const AnnotationMapTestWrapper: React.FC<AnnotationMapProps> = (
  props
) => {
  return (
    <MemoryRouter>
      <AnnotationMap {...props} />
    </MemoryRouter>
  );
};
