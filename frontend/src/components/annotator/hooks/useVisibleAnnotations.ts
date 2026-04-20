import { useMemo } from "react";
import { useAllAnnotations } from "./useAllAnnotations";
import { useAnnotationDisplay } from "../context/UISettingsAtom";
import { useAnnotationControls } from "../context/UISettingsAtom";
import { useAnnotationSelection } from "../context/UISettingsAtom";
import { usePdfAnnotations } from "./AnnotationHooks";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../types/annotations";

/**
 * Returns the set of annotations that should be visible given the current
 * view / filter settings.
 *
 * The logic exactly mirrors the filtering previously duplicated in
 * PDFPage.tsx and AnnotationList.tsx, so that both components (and any
 * future components) can rely on a single source of truth.
 */
export function useVisibleAnnotations(): (
  | ServerTokenAnnotation
  | ServerSpanAnnotation
)[] {
  /* ---------------- raw data ---------------------------------------- */
  const allAnnotations = useAllAnnotations();
  const { pdfAnnotations } = usePdfAnnotations();

  /* ---------------- ui-state ---------------------------------------- */
  const { showStructural, showStructuralRelationships, showSelectedOnly } =
    useAnnotationDisplay();

  const { spanLabelsToView } = useAnnotationControls();

  const { selectedAnnotations, selectedRelations } = useAnnotationSelection();

  /* ---------------- filtering --------------------------------------- */
  return useMemo(() => {
    /* ---- ①  IDs that must be visible whatever other filters say ---- */
    const forcedBySelectedRelationIds = new Set<string>(
      selectedRelations.flatMap((rel) => [...rel.sourceIds, ...rel.targetIds])
    );

    /* always show the annotation that is currently selected                */
    const forcedBySelection = new Set<string>(selectedAnnotations);

    const forcedByRelationships = new Set<string>();
    if (showStructuralRelationships) {
      (pdfAnnotations?.relations ?? []).forEach((rel) => {
        rel.sourceIds.forEach((id) => forcedByRelationships.add(id));
        rel.targetIds.forEach((id) => forcedByRelationships.add(id));
      });
    }

    const forcedIds = new Set(forcedBySelection);

    // Explicit relation selection always wins — not gated on showStructural (unlike forcedByRelationships).
    forcedBySelectedRelationIds.forEach((id) => forcedIds.add(id));

    if (showStructural) {
      forcedByRelationships.forEach((id) => forcedIds.add(id));
    }

    /* ---- ②  Helper for label filter -------------------------------- */
    const labelFilterActive =
      spanLabelsToView && spanLabelsToView.length > 0
        ? new Set(spanLabelsToView.map((l) => l.id))
        : null;

    /* ---- ③  Final predicate ---------------------------------------- */
    return allAnnotations.filter((annot) => {
      /* forced – always keep                                            */
      if (forcedIds.has(annot.id)) {
        return true;
      }

      /* showSelectedOnly filter - only show selected annotations and their connections */
      if (showSelectedOnly) {
        // Only show if annotation is selected or connected to a selected relationship
        const isConnected = (pdfAnnotations?.relations ?? []).some(
          (rel) =>
            selectedRelations.includes(rel) &&
            (rel.sourceIds.includes(annot.id) ||
              rel.targetIds.includes(annot.id))
        );
        if (!selectedAnnotations.includes(annot.id) && !isConnected) {
          return false;
        }
      }

      /* structural filter - hide structural annotations if showStructural is false */
      if (annot.structural && !showStructural) {
        return false;
      }

      /* label filter - applies to both structural and non-structural    */
      if (
        labelFilterActive &&
        !labelFilterActive.has(annot.annotationLabel.id)
      ) {
        return false;
      }

      return true;
    });
  }, [
    allAnnotations,
    showStructural,
    showStructuralRelationships,
    showSelectedOnly,
    spanLabelsToView,
    selectedAnnotations,
    selectedRelations,
    pdfAnnotations?.relations,
  ]);
}
