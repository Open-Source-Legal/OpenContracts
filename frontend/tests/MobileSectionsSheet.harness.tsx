import React, { useEffect } from "react";
import { MemoryRouter } from "react-router-dom";
import { Provider, useSetAtom } from "jotai";

import { MobileSectionsSheet } from "../src/components/knowledge_base/document/layouts/mobile/MobileSectionsSheet";
import { structuralAnnotationsAtom } from "../src/components/annotator/context/AnnotationAtoms";
import type { ServerTokenAnnotation } from "../src/components/annotator/types/annotations";

/** Minimal shape {@link MobileSectionsSheet} reads off each structural item. */
export interface StubSection {
  id: string;
  rawText: string;
  page: number;
  labelText?: string;
}

/** Seeds the structural-annotations atom with the supplied stub sections. */
const SectionSeeder: React.FC<{ sections: StubSection[] }> = ({ sections }) => {
  const setStructural = useSetAtom(structuralAnnotationsAtom);
  useEffect(() => {
    setStructural(
      sections.map(
        (s) =>
          ({
            id: s.id,
            rawText: s.rawText,
            page: s.page,
            annotationLabel: { text: s.labelText ?? "Section" },
          } as unknown as ServerTokenAnnotation)
      )
    );
  }, [sections, setStructural]);
  return null;
};

/**
 * Test harness for {@link MobileSectionsSheet}. Wraps the sheet in a router
 * (the sheet flips the `structural` URL param on open) and an isolated Jotai
 * store seeded with stub structural annotations.
 */
export const MobileSectionsSheetHarness: React.FC<{
  open?: boolean;
  sections?: StubSection[];
  onNavigate?: (annotationId: string) => void;
}> = ({ open = true, sections = [], onNavigate = () => {} }) => (
  <MemoryRouter>
    <Provider>
      <SectionSeeder sections={sections} />
      <MobileSectionsSheet open={open} onNavigate={onNavigate} />
    </Provider>
  </MemoryRouter>
);
