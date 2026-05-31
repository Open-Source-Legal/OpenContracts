import React from "react";
import { AnnotationMap } from "../src/components/maps/AnnotationMap";
import type { AnnotationMapProps } from "../src/components/maps/types";

/**
 * Test wrapper for {@link AnnotationMap}.
 *
 * AnnotationMap is route-agnostic (document navigation is delegated to the
 * caller via `onSelectDocument`) and performs no queries of its own, so it
 * needs no Router/Apollo context — it simply takes pins as a prop.
 *
 * Per CLAUDE.md pitfall #16, the `.ct.tsx` file imports THIS wrapper component
 * in its own import statement, separate from helper/fixture imports.
 */
export const AnnotationMapTestWrapper: React.FC<AnnotationMapProps> = (
  props
) => {
  return <AnnotationMap {...props} />;
};
