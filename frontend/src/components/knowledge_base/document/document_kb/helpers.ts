import { AnnotationLabelType } from "../../../../types/graphql-api";
import { RelationGroup } from "../../../annotator/types/annotations";

interface RawRelation {
  id: string;
  structural?: boolean;
  relationshipLabel: AnnotationLabelType;
  sourceAnnotations: { edges: Array<{ node?: { id: string } | null } | null> };
  targetAnnotations: { edges: Array<{ node?: { id: string } | null } | null> };
}

/**
 * Convert a GraphQL relationship payload into a `RelationGroup`.
 *
 * Both the structural-lazy-load path and the bulk-document-load path map the
 * same shape, so the construction lives in one place to keep callers in
 * lockstep if `RelationGroup`'s constructor signature changes.
 *
 * `forceStructural` flips relationships to structural=true unconditionally —
 * used by the lazy structural loader where the wire format omits `structural`
 * but every result is structural by definition.
 */
export const relationToGroup = (
  rel: RawRelation,
  forceStructural?: boolean
): RelationGroup =>
  new RelationGroup(
    rel.sourceAnnotations.edges
      .map((edge) => edge?.node?.id)
      .filter((id): id is string => id !== undefined),
    rel.targetAnnotations.edges
      .map((edge) => edge?.node?.id)
      .filter((id): id is string => id !== undefined),
    rel.relationshipLabel,
    rel.id,
    forceStructural ?? rel.structural ?? false
  );
