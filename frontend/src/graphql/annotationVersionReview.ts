import { gql } from "@apollo/client";
import { RawServerAnnotationType } from "../types/graphql-api";

/**
 * How an annotation crossed a document version. ``AUTO`` (machine-carried
 * exact match) and ``STALE`` (no match) await a person; the rest are that
 * person's decision.
 */
export type AnnotationVersionState =
  | "AUTO"
  | "STALE"
  | "REAPPROVED"
  | "CORRECTED"
  | "DROPPED";

export const PENDING_VERSION_STATES: ReadonlySet<AnnotationVersionState> =
  new Set(["AUTO", "STALE"]);

export const VERSION_STATE_LABELS: Record<AnnotationVersionState, string> = {
  AUTO: "Auto-carried · unreviewed",
  STALE: "Needs placement",
  REAPPROVED: "Approved",
  CORRECTED: "Corrected",
  DROPPED: "Dropped",
};

export interface AnnotationReviewRow {
  annotation: RawServerAnnotationType;
  state: AnnotationVersionState;
  successor?: RawServerAnnotationType | null;
  reviewedBy?: { slug?: string | null } | null;
  reviewedAt?: string | null;
}

export const GET_ANNOTATION_REVIEW_STATUS = gql`
  query AnnotationReviewStatus($documentId: ID!, $corpusId: ID!) {
    document(id: $documentId) {
      id
      isCurrent
      parent {
        id
      }
      annotationsNeedingReview(corpusId: $corpusId)
    }
  }
`;

const REVIEW_FIELDS = gql`
  fragment AnnotationReviewFields on AnnotationVersionReview {
    state
    reviewedBy {
      slug
    }
    reviewedAt
    annotation {
      id
      rawText
      page
      json
      annotationType
      versionState
      annotationLabel {
        id
        text
        color
        icon
        description
        labelType
      }
    }
    successor {
      id
      rawText
      page
      json
      annotationType
      structural
      myPermissions
      linkUrl
      versionState
      annotationLabel {
        id
        text
        color
        icon
        description
        labelType
      }
    }
  }
`;

export const GET_ANNOTATION_VERSION_REVIEW = gql`
  query AnnotationVersionReview($documentId: ID!, $corpusId: ID!) {
    annotationVersionReview(documentId: $documentId, corpusId: $corpusId) {
      ...AnnotationReviewFields
    }
  }
  ${REVIEW_FIELDS}
`;

export const CARRY_FORWARD_ANNOTATION = gql`
  mutation CarryForwardAnnotation(
    $annotationId: ID!
    $targetDocumentId: ID!
    $placement: GenericScalar
    $annotationLabelId: ID
  ) {
    carryForwardAnnotation(
      annotationId: $annotationId
      targetDocumentId: $targetDocumentId
      placement: $placement
      annotationLabelId: $annotationLabelId
    ) {
      ...AnnotationReviewFields
    }
  }
  ${REVIEW_FIELDS}
`;

export const DROP_STALE_ANNOTATION = gql`
  mutation DropStaleAnnotation($annotationId: ID!, $targetDocumentId: ID!) {
    dropStaleAnnotation(
      annotationId: $annotationId
      targetDocumentId: $targetDocumentId
    ) {
      ...AnnotationReviewFields
    }
  }
  ${REVIEW_FIELDS}
`;

// ``GetDocumentAnnotationsOnly`` is deliberately absent: its only observer is
// a ``skip: true`` handle, so Apollo parks it in standby and a name refetch
// only logs a warning. Decisions reach the viewer through the mutation result.
export const REVIEW_REFETCH_QUERIES = [
  "AnnotationReviewStatus",
  "AnnotationVersionReview",
];
