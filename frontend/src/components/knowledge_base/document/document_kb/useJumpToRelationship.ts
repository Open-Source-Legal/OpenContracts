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
import { getNumericIdFromGlobalId } from "../../../../utils/idValidation";
import { JUMP_TO_RELATIONSHIP_SCROLL_RETRY_MS } from "../../../../assets/configurations/constants";

export function useJumpToRelationship(): void {
  const relId = useReactiveVar(selectedRelationshipId);
  const allRelations = useAtomValue(allRelationsAtom);
  const [, setSelectedRelations] = useAtom(selectedRelationsAtom);
  const [, setHoveredAnnotationId] = useAtom(hoveredAnnotationIdAtom);
  const { annotationElementRefs } = useAnnotationRefs();

  // Two separate "applied once" guards:
  // * ``lastAppliedSelectionRef`` — set as soon as the selection has been
  //   pushed to ``selectedRelationsAtom``. Prevents the effect from
  //   re-selecting the URL-driven relationship on every ``allRelations``
  //   mutation, so user-driven edits aren't fought.
  // * ``lastAppliedScrollRef`` — set only when ``scrollIntoView`` actually
  //   fired. The source/target annotation refs come from a virtualised
  //   renderer; for deep-links into pages the renderer hasn't materialised
  //   yet, the refs map is empty on the first run and the scroll has to
  //   retry once ``annotationElementRefs`` (a Jotai atom) repopulates with
  //   the newly-mounted page. Selection without scroll is still useful
  //   (the relation line will render once the user scrolls there
  //   manually), so the two are tracked independently.
  const lastAppliedSelectionRef = useRef<string | null>(null);
  const lastAppliedScrollRef = useRef<string | null>(null);

  useEffect(() => {
    if (!relId) {
      // ``rel=`` was cleared — drop any URL-driven selection so the
      // viewer reverts to the user's local interaction state. We don't
      // touch ``setSelectedAnnotations`` here because that's driven by
      // the ``ann=`` param via its own routing path. Also clear the
      // hover indicator since we set it when applying the jump.
      if (lastAppliedSelectionRef.current !== null) {
        setSelectedRelations([]);
        setHoveredAnnotationId(null);
        lastAppliedSelectionRef.current = null;
        lastAppliedScrollRef.current = null;
      }
      return;
    }

    // ``relId`` is a raw Django PK (URL convention, see ``cache.ts``)
    // but ``RelationGroup.id`` carries the Relay global ID from
    // GraphQL. Compare on the numeric PK so the deep-link actually
    // matches.
    const relPk = parseInt(relId, 10);
    if (Number.isNaN(relPk)) {
      return;
    }
    const match: RelationGroup | undefined = allRelations.find((r) => {
      try {
        return getNumericIdFromGlobalId(r.id) === relPk;
      } catch {
        return false;
      }
    });
    if (!match) {
      // Relations not yet loaded for this document. Bail out — the
      // effect will re-run when ``allRelations`` populates (it's an
      // atom and triggers a render on change).
      return;
    }

    if (lastAppliedSelectionRef.current !== relId) {
      setSelectedRelations([match]);
      lastAppliedSelectionRef.current = relId;
    }

    // We pick the source over the targets because the source is the
    // block's anchor — most users want to read from the top down.
    // Falls back to the first available ref if the source hasn't been
    // mounted yet (e.g. when the source lives on a page that the
    // virtualised renderer hasn't materialised). When no ref is
    // available we leave ``lastAppliedScrollRef`` unset so the effect
    // retries once the relevant page mounts.
    const tryScroll = (): boolean => {
      const refs = annotationElementRefs?.current ?? {};
      const candidateIds = [...match.sourceIds, ...match.targetIds];
      const targetId = candidateIds.find((id) => refs[id]);
      const ref = targetId ? refs[targetId] : undefined;
      if (ref && typeof ref.scrollIntoView === "function") {
        ref.scrollIntoView({ behavior: "smooth", block: "center" });
        if (match.sourceIds[0]) {
          setHoveredAnnotationId(match.sourceIds[0]);
        }
        lastAppliedScrollRef.current = relId;
        return true;
      }
      return false;
    };

    if (lastAppliedScrollRef.current !== relId && !tryScroll()) {
      // Defensive fallback: when the deep-link lands on a page the
      // virtualised PDF renderer hasn't materialised yet, refs register
      // asynchronously as the page mounts. The atom-driven re-render
      // path handles the common case, but a few render orderings (e.g.
      // when ``allRelations`` re-emits before the page actually paints)
      // can leave the effect waiting indefinitely. Schedule one delayed
      // retry that re-reads the refs map and clear it if the effect re-
      // runs first, so the timer never re-fires after the user has
      // already navigated elsewhere.
      const handle = window.setTimeout(() => {
        if (lastAppliedScrollRef.current !== relId) {
          tryScroll();
        }
      }, JUMP_TO_RELATIONSHIP_SCROLL_RETRY_MS);
      return () => window.clearTimeout(handle);
    }
  }, [
    relId,
    allRelations,
    setSelectedRelations,
    setHoveredAnnotationId,
    annotationElementRefs,
  ]);
}
