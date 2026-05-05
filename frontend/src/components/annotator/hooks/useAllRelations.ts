import { useAtomValue } from "jotai";
import { allRelationsAtom } from "../context/AnnotationAtoms";
import { RelationGroup } from "../types/annotations";

/**
 * Returns the global, duplicate-free relation array — the union of
 * user-editable relations from ``pdfAnnotationsAtom.relations`` and
 * structural relations from ``structuralRelationshipsAtom``.
 *
 * Use this in any consumer that needs to reason about the full relation
 * set (e.g. ``showStructuralRelationships`` visibility logic). For
 * relation CRUD on the user-editable subset, read ``pdfAnnotations.relations``
 * directly.
 */
export function useAllRelations(): RelationGroup[] {
  return useAtomValue(allRelationsAtom);
}
