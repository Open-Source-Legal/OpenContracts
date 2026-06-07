/**
 * Pure helpers used by ``CorpusAnnotationCards`` — extracted so the
 * blockContext deep-link wiring can be unit-tested without mounting the
 * full component (which depends on Apollo, router, and several reactive
 * vars). Issue #1645.
 */

import type { SemanticSearchResult } from "../../graphql/queries";

/** Subset of ``ServerAnnotationType`` that the helpers actually read. */
export type AnnotationLike = {
  id: string;
  analysis?: { id: string } | null;
};

/** Shape of the queryParams payload consumed by ``getDocumentUrl``. */
export interface AnnotationClickQueryParams {
  annotationIds: string[];
  analysisIds?: string[];
  relationshipId?: string;
}

/**
 * Build the annotation-id → containing OC_SUBTREE_GROUP relationship-id
 * lookup that drives the "jump to block" deep-link on semantic search
 * result clicks. Returns an empty map when not in semantic mode or when
 * no result carries a ``blockContext.relationshipId``.
 */
export function buildBlockRelationshipIdMap(
  isSemanticSearchActive: boolean,
  results: SemanticSearchResult[]
): Map<string, string> {
  const map = new Map<string, string>();
  if (!isSemanticSearchActive) return map;
  for (const result of results) {
    const relId = result.blockContext?.relationshipId;
    if (relId) {
      map.set(result.annotation.id, relId);
    }
  }
  return map;
}

/**
 * Resolve which corpus a card's deep link should open in. Structural
 * annotations are corpus-agnostic (``corpus_id=NULL``), so
 * ``annotation.corpus`` is absent for them; fall back to the corpus
 * currently being viewed so the link opens the document in-corpus
 * (``/d/<user>/<corpus>/<doc>``) rather than standalone. Returns ``null``
 * (never ``undefined``) so it slots directly into ``getDocumentUrl``.
 */
export function resolveDeepLinkCorpus<C>(
  annotationCorpus: C | null | undefined,
  openedCorpus: C | null | undefined
): C | null {
  return annotationCorpus ?? openedCorpus ?? null;
}

/**
 * Build the query-params object passed to ``getDocumentUrl`` for an
 * annotation card click. Includes the analysis id when the annotation
 * was created by one and the containing-block relationship id when the
 * search result carried one.
 */
export function buildAnnotationClickQueryParams(
  annotation: AnnotationLike,
  blockRelationshipIdMap: Map<string, string>
): AnnotationClickQueryParams {
  const params: AnnotationClickQueryParams = {
    annotationIds: [annotation.id],
  };
  if (annotation.analysis?.id) {
    params.analysisIds = [annotation.analysis.id];
  }
  const blockRelationshipId = blockRelationshipIdMap.get(annotation.id);
  if (blockRelationshipId) {
    params.relationshipId = blockRelationshipId;
  }
  return params;
}
