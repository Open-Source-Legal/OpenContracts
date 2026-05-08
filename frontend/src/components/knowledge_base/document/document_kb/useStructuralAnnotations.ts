import { useEffect } from "react";
import { useLazyQuery, useReactiveVar } from "@apollo/client";
import { useAtom } from "jotai";
import {
  GET_DOCUMENT_STRUCTURAL_ANNOTATIONS,
  GetDocumentStructuralAnnotationsInput,
  GetDocumentStructuralAnnotationsOutput,
} from "../../../../graphql/queries";
import {
  structuralAnnotationsAtom,
  structuralAnnotationsLoadedAtom,
  structuralRelationshipsAtom,
} from "../../../annotator/context/AnnotationAtoms";
import {
  selectedAnnotationIds,
  showStructuralAnnotations,
} from "../../../../graphql/cache";
import { convertToServerAnnotation } from "../../../../utils/transform";
import { relationToGroup } from "./helpers";

/**
 * Lazy-loads structural annotations (headers, sections, paragraphs) for the
 * current document.
 *
 * Two separate fetch paths:
 * - **All structural** — fetched once when the user toggles structural
 *   visibility on, marks `structuralAnnotationsLoaded` true so we never
 *   double-fetch.
 * - **Targeted by ID** — fetched when an `?ann=<id>` deep-link references
 *   one or more annotations and the full set hasn't been loaded yet. Merges
 *   into the existing atoms by id so the targeted fetch can't drop entries.
 *
 * Both fetches reuse `GET_DOCUMENT_STRUCTURAL_ANNOTATIONS` but bind to
 * separate `useLazyQuery` refs to avoid a shared-ref race between the two
 * paths (Apollo would otherwise reuse the last completion handler).
 *
 * Resets all three atoms on `documentId` change so a stale partial load from
 * the previous document can never bleed into the new one.
 */
export function useStructuralAnnotations(documentId: string): void {
  const [, setStructuralAnnotations] = useAtom(structuralAnnotationsAtom);
  const [, setStructuralRelationships] = useAtom(structuralRelationshipsAtom);
  const [structuralAnnotationsLoaded, setStructuralAnnotationsLoaded] = useAtom(
    structuralAnnotationsLoadedAtom
  );

  const showStructural = useReactiveVar(showStructuralAnnotations);
  const deepLinkedAnnotationIds = useReactiveVar(selectedAnnotationIds);

  const [fetchAllStructural] = useLazyQuery<
    GetDocumentStructuralAnnotationsOutput,
    GetDocumentStructuralAnnotationsInput
  >(GET_DOCUMENT_STRUCTURAL_ANNOTATIONS, {
    fetchPolicy: "cache-and-network",
    onCompleted: (data) => {
      if (data?.document?.allStructuralAnnotations) {
        const structuralAnns = data.document.allStructuralAnnotations.map(
          (ann) => convertToServerAnnotation(ann)
        );
        setStructuralAnnotations(structuralAnns);
        setStructuralAnnotationsLoaded(true);
      }
      if (data?.document?.allStructuralRelationships) {
        const structuralRels = data.document.allStructuralRelationships.map(
          (rel) => relationToGroup(rel, true)
        );
        setStructuralRelationships(structuralRels);
      }
    },
  });

  const [fetchTargetedStructural] = useLazyQuery<
    GetDocumentStructuralAnnotationsOutput,
    GetDocumentStructuralAnnotationsInput
  >(GET_DOCUMENT_STRUCTURAL_ANNOTATIONS, {
    fetchPolicy: "cache-and-network",
    onCompleted: (data) => {
      if (data?.document?.allStructuralAnnotations) {
        const structuralAnns = data.document.allStructuralAnnotations.map(
          (ann) => convertToServerAnnotation(ann)
        );
        setStructuralAnnotations((prev) => {
          const existingIds = new Set(prev.map((a) => a.id));
          const newAnns = structuralAnns.filter((a) => !existingIds.has(a.id));
          return newAnns.length > 0 ? [...prev, ...newAnns] : prev;
        });
      }
      // Targeted fetch returns the document's full structural relationship
      // set (the optimizer ignores annotation IDs for relationships) — merge
      // by id so we don't drop already-loaded entries.
      if (data?.document?.allStructuralRelationships) {
        const structuralRels = data.document.allStructuralRelationships.map(
          (rel) => relationToGroup(rel, true)
        );
        setStructuralRelationships((prev) => {
          const existingIds = new Set(prev.map((r) => r.id));
          const newRels = structuralRels.filter((r) => !existingIds.has(r.id));
          return newRels.length > 0 ? [...prev, ...newRels] : prev;
        });
      }
    },
  });

  // Reset when navigating to a different document.
  useEffect(() => {
    setStructuralAnnotationsLoaded(false);
    setStructuralAnnotations([]);
    setStructuralRelationships([]);
  }, [
    documentId,
    setStructuralAnnotationsLoaded,
    setStructuralAnnotations,
    setStructuralRelationships,
  ]);

  // Fetch ALL structural annotations when user toggles structural visibility.
  useEffect(() => {
    if (showStructural && !structuralAnnotationsLoaded && documentId) {
      fetchAllStructural({ variables: { documentId } });
    }
  }, [
    showStructural,
    structuralAnnotationsLoaded,
    documentId,
    fetchAllStructural,
  ]);

  // Fetch ONLY the deep-linked annotations when navigating via URL.
  // selectedAnnotationIds may contain non-structural IDs (e.g. corpus
  // annotations from URL deep-links). The backend returns an empty list for
  // those — accepted trade-off to avoid needing annotation type metadata
  // before the fetch.
  useEffect(() => {
    if (
      deepLinkedAnnotationIds.length > 0 &&
      documentId &&
      !structuralAnnotationsLoaded
    ) {
      fetchTargetedStructural({
        variables: { documentId, annotationIds: deepLinkedAnnotationIds },
      });
    }
  }, [
    deepLinkedAnnotationIds,
    documentId,
    structuralAnnotationsLoaded,
    fetchTargetedStructural,
  ]);
}
