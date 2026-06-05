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
 *
 * Returns `{ loading }` reflecting the **targeted** deep-link fetch only. A
 * deep-link to a structural annotation (`?ann=<id>`) resolves via the targeted
 * lazy query, which fires *after* the corpus/document queries (and therefore
 * after the document loader's own `loading` has already dropped to false).
 * Surfacing this lets callers OR it into their not-found guard so a structural
 * deep-link shows a loader instead of briefly flashing "no longer available".
 * The all-structural toggle fetch is deliberately excluded: it only runs when
 * the user turns structural visibility on, and folding it into a shared loading
 * flag would make unrelated surfaces flash loading on that toggle.
 *
 * The flag also covers the window *before* the targeted query is dispatched:
 * its effect runs only after the render that needs it, so for one frame
 * `targetedStructuralResult` reads `{ called: false, loading: false }`.
 * Reporting that pending window as loading (by mirroring the effect's own
 * guard) keeps the loader continuous from the first render until the fetch
 * settles, closing the one-frame not-found flash entirely rather than merely
 * shortening it.
 */
export function useStructuralAnnotations(documentId: string): {
  loading: boolean;
} {
  const [, setStructuralAnnotations] = useAtom(structuralAnnotationsAtom);
  const [, setStructuralRelationships] = useAtom(structuralRelationshipsAtom);
  const [structuralAnnotationsLoaded, setStructuralAnnotationsLoaded] = useAtom(
    structuralAnnotationsLoadedAtom
  );

  const showStructural = useReactiveVar(showStructuralAnnotations);
  const deepLinkedAnnotationIds = useReactiveVar(selectedAnnotationIds);

  // ``useLazyQuery`` exposes ``data`` from the latest completion. We
  // intentionally do NOT use ``onCompleted`` here: with
  // ``fetchPolicy: "cache-and-network"`` Apollo fires ``onCompleted``
  // twice per call — once for the cached result and again for the
  // network response. The all-structural path's "replace" semantics
  // would then overwrite optimistic merges from the targeted path on
  // the second fire. Reading ``data`` from a ``useEffect`` makes the
  // cached/network rerun behaviour explicit and idempotent.
  const [fetchAllStructural, allStructuralResult] = useLazyQuery<
    GetDocumentStructuralAnnotationsOutput,
    GetDocumentStructuralAnnotationsInput
  >(GET_DOCUMENT_STRUCTURAL_ANNOTATIONS, {
    fetchPolicy: "cache-and-network",
  });

  const [fetchTargetedStructural, targetedStructuralResult] = useLazyQuery<
    GetDocumentStructuralAnnotationsOutput,
    GetDocumentStructuralAnnotationsInput
  >(GET_DOCUMENT_STRUCTURAL_ANNOTATIONS, {
    fetchPolicy: "cache-and-network",
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

  // Apply the all-structural result to atoms when ``data`` settles.
  // ``cache-and-network`` will fire this twice per fetch — the second
  // run is a no-op because ``setStructuralAnnotationsLoaded(true)`` has
  // already gated future fetches and the array shape is identical.
  useEffect(() => {
    const data = allStructuralResult.data;
    if (!data?.document) return;
    if (data.document.allStructuralAnnotations) {
      const structuralAnns = data.document.allStructuralAnnotations.map((ann) =>
        convertToServerAnnotation(ann)
      );
      setStructuralAnnotations(structuralAnns);
      setStructuralAnnotationsLoaded(true);
    }
    if (data.document.allStructuralRelationships) {
      const structuralRels = data.document.allStructuralRelationships.map(
        (rel) => relationToGroup(rel, true)
      );
      setStructuralRelationships(structuralRels);
    }
  }, [
    allStructuralResult.data,
    setStructuralAnnotations,
    setStructuralAnnotationsLoaded,
    setStructuralRelationships,
  ]);

  // Apply the targeted-fetch result by merging into existing atom state.
  // Idempotent across the cache + network fires because the merge is
  // keyed on ``id``.
  useEffect(() => {
    const data = targetedStructuralResult.data;
    if (!data?.document) return;
    if (data.document.allStructuralAnnotations) {
      const structuralAnns = data.document.allStructuralAnnotations.map((ann) =>
        convertToServerAnnotation(ann)
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
    if (data.document.allStructuralRelationships) {
      const structuralRels = data.document.allStructuralRelationships.map(
        (rel) => relationToGroup(rel, true)
      );
      setStructuralRelationships((prev) => {
        const existingIds = new Set(prev.map((r) => r.id));
        const newRels = structuralRels.filter((r) => !existingIds.has(r.id));
        return newRels.length > 0 ? [...prev, ...newRels] : prev;
      });
    }
  }, [
    targetedStructuralResult.data,
    setStructuralAnnotations,
    setStructuralRelationships,
  ]);

  // The targeted lazy query is dispatched by the effect above, which runs only
  // *after* this render commits. Until then `targetedStructuralResult` reads
  // `{ called: false, loading: false }`, so returning its raw `loading` would
  // leave a one-frame gap where a structural `?ann=<id>` deep-link flashes the
  // not-found message. Mirror the dispatch effect's own guard to treat that
  // pending window as loading; once the fetch is dispatched (`called` latches
  // true) we defer to the query's real `loading`. This can't get stuck: the
  // targeted path deliberately leaves `structuralAnnotationsLoaded` false, but
  // `called` stays true, so a genuinely-missing annotation still settles to
  // `loading: false` and surfaces the not-found state.
  const targetedFetchPending =
    deepLinkedAnnotationIds.length > 0 &&
    !!documentId &&
    !structuralAnnotationsLoaded &&
    !targetedStructuralResult.called;

  return {
    loading: targetedFetchPending || targetedStructuralResult.loading,
  };
}
