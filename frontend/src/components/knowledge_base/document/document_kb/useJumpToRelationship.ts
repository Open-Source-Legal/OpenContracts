/**
 * useJumpToRelationship — wire the URL ``?rel=<pk>`` parameter to the
 * doc viewer's existing relation-selection plumbing.
 *
 * Issue #1645: semantic search can now surface OC_SUBTREE_GROUP
 * relationships. When a user clicks a relationship hit, the search UI
 * navigates to the document with ``?rel=<pk>&ann=<src>,<t1>,...`` set.
 * On arrival the doc viewer needs to:
 *  - Select the relation as a whole so the relation line renders
 *    (``selectedRelationsAtom``).
 *  - Ensure ``selectedAnnotationIds`` (URL-driven) lines up with the
 *    relation's source/target IDs — already handled by the existing
 *    ``ann`` param; the consumer adds it client-side when constructing
 *    the URL.
 *  - Scroll the source annotation into view (matches how
 *    ``ContentItemRenderer.handleSelectRelation`` behaves for in-app
 *    selections).
 *
 * The hook is a no-op when ``selectedRelationshipId`` is null. It waits
 * for the relation list to populate (structural relations are lazy-
 * loaded by ``useStructuralAnnotations``); once a match is found the
 * selection is applied EXACTLY once per id change, so user-driven
 * navigation after the initial jump isn't fought by re-runs of this
 * effect.
 */

import { useEffect, useRef } from "react";
import { useReactiveVar } from "@apollo/client";
import { useAtom, useAtomValue } from "jotai";
import { selectedRelationshipId } from "../../../../graphql/cache";
import {
  selectedRelationsAtom,
  hoveredAnnotationIdAtom,
} from "../../../annotator/context/UISettingsAtom";
import { allRelationsAtom } from "../../../annotator/context/AnnotationAtoms";
import { useAnnotationRefs } from "../../../annotator/hooks/useAnnotationRefs";
import { RelationGroup } from "../../../annotator/types/annotations";

export function useJumpToRelationship(): void {
  const relId = useReactiveVar(selectedRelationshipId);
  const allRelations = useAtomValue(allRelationsAtom);
  const [, setSelectedRelations] = useAtom(selectedRelationsAtom);
  const [, setHoveredAnnotationId] = useAtom(hoveredAnnotationIdAtom);
  const { annotationElementRefs } = useAnnotationRefs();

  // Track the last id we applied so the effect doesn't re-run on every
  // ``allRelations`` mutation (relation CRUD elsewhere would otherwise
  // re-select the URL-driven relationship and pull focus back to it).
  const lastAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!relId) {
      // ``rel=`` was cleared — drop any URL-driven selection so the
      // viewer reverts to the user's local interaction state. We don't
      // touch ``setSelectedAnnotations`` here because that's driven by
      // the ``ann=`` param via its own routing path.
      if (lastAppliedRef.current !== null) {
        setSelectedRelations([]);
        lastAppliedRef.current = null;
      }
      return;
    }

    if (lastAppliedRef.current === relId) {
      // Already applied this id — leave the user's subsequent edits alone.
      return;
    }

    const match: RelationGroup | undefined = allRelations.find(
      (r) => r.id === relId
    );
    if (!match) {
      // Relations not yet loaded for this document. Bail out — the
      // effect will re-run when ``allRelations`` populates (it's an
      // atom and triggers a render on change).
      return;
    }

    setSelectedRelations([match]);

    // Smooth-scroll the source annotation into view so the user lands
    // on the block root, then surface a hover indicator so the relation
    // line is unambiguous. We pick the source over the targets because
    // the source is the block's anchor — most users want to read from
    // the top down. Falls back to the first available ref if the source
    // hasn't been mounted yet (e.g. when the source lives on a page
    // that the virtualised renderer hasn't materialised).
    const refs = annotationElementRefs?.current ?? {};
    const candidateIds = [...match.sourceIds, ...match.targetIds];
    const targetId = candidateIds.find((id) => refs[id]);
    const ref = targetId ? refs[targetId] : undefined;
    if (ref && typeof ref.scrollIntoView === "function") {
      ref.scrollIntoView({ behavior: "smooth", block: "center" });
      if (match.sourceIds[0]) {
        setHoveredAnnotationId(match.sourceIds[0]);
      }
    }

    lastAppliedRef.current = relId;
  }, [
    relId,
    allRelations,
    setSelectedRelations,
    setHoveredAnnotationId,
    annotationElementRefs,
  ]);
}
