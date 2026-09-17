import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { useAtom, useSetAtom, useStore } from "jotai";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  AnnotationReviewRow,
  CARRY_FORWARD_ANNOTATION,
  DROP_STALE_ANNOTATION,
  GET_ANNOTATION_REVIEW_STATUS,
  GET_ANNOTATION_VERSION_REVIEW,
  REVIEW_REFETCH_QUERIES,
  VERSION_STATE_LABELS,
} from "../../../graphql/annotationVersionReview";
import { pendingAnnotationReviewAtom } from "../../annotator/context/AnnotationReviewAtom";
import { activeSpanLabelAtom } from "../../annotator/context/AnnotationControlAtoms";
import { usePdfAnnotations } from "../../annotator/hooks/AnnotationHooks";
import {
  convertToServerAnnotation,
  convertToDocTypeAnnotation,
} from "../../../utils/transform";
import { LabelType } from "../../../types/graphql-api";
import { selectedDocumentAtom } from "../../annotator/context/DocumentAtom";

const Review = styled.section`
  padding: 0.5rem 0;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textPrimary};
  button {
    cursor: pointer;
    padding: 0.35rem 0.6rem;
    margin-right: 0.4rem;
    min-height: 32px;
    border: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 6px;
    background: white;
    color: inherit;
  }
  button:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.primaryBlue};
    outline-offset: 2px;
  }
  button:hover:not(:disabled) {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
  button:disabled {
    cursor: default;
    opacity: 0.5;
  }
  .rows {
    max-height: 32vh;
    overflow-y: auto;
  }
  article {
    padding: 0.7rem;
    margin-top: 0.5rem;
    border: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 8px;
  }
  blockquote {
    margin: 0.4rem 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  @media (max-width: 768px) {
    button {
      min-height: 44px;
    }
  }
`;

export function AnnotationVersionReviewPanel({
  documentId,
  corpusId,
  readOnly,
  onPlace,
}: {
  documentId: string;
  corpusId: string;
  readOnly: boolean;
  onPlace: () => void;
}) {
  const store = useStore();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useAtom(pendingAnnotationReviewAtom);
  const setLabel = useSetAtom(activeSpanLabelAtom);
  const { pdfAnnotations, addMultipleAnnotations, addDocTypeAnnotations } =
    usePdfAnnotations();
  const { data: status } = useQuery(GET_ANNOTATION_REVIEW_STATUS, {
    variables: { documentId, corpusId },
  });
  const { data, loading, error } = useQuery<{
    annotationVersionReview: AnnotationReviewRow[];
  }>(GET_ANNOTATION_VERSION_REVIEW, {
    variables: { documentId, corpusId },
    skip: !open,
    fetchPolicy: "cache-and-network",
  });
  const [carry, { loading: carrying }] = useMutation<{
    carryForwardAnnotation: AnnotationReviewRow;
  }>(CARRY_FORWARD_ANNOTATION, { refetchQueries: REVIEW_REFETCH_QUERIES });
  const [drop, { loading: dropping }] = useMutation(DROP_STALE_ANNOTATION, {
    refetchQueries: REVIEW_REFETCH_QUERIES,
  });
  useEffect(() => {
    setOpen(false);
    setMessage("");
    return () => setPending(null);
  }, [documentId, corpusId, setPending]);

  const reviewPending =
    pending?.documentId === documentId && pending.corpusId === corpusId;
  if (status?.document && !status.document.isCurrent) {
    return (
      <Review aria-label="Document label review">
        {pdfAnnotations.docTypes
          .filter((annotation) => annotation.versionState)
          .map((annotation) => (
            <span key={annotation.id}>
              {annotation.annotationLabel.text} ·{" "}
              {VERSION_STATE_LABELS[annotation.versionState!]}{" "}
            </span>
          ))}
      </Review>
    );
  }
  if (!status?.document?.parent) return null;
  const count = status.document.staleAnnotationCount;
  const busy = carrying || dropping;
  const decide = async (row: AnnotationReviewRow, approve: boolean) => {
    setMessage("");
    try {
      const variables = {
        annotationId: row.annotation.id,
        targetDocumentId: documentId,
      };
      if (approve) {
        const result = await carry({ variables });
        if (store.get(selectedDocumentAtom)?.id !== documentId) return;
        const successor = result.data?.carryForwardAnnotation.successor;
        if (successor?.annotationType === LabelType.DocTypeLabel) {
          addDocTypeAnnotations([convertToDocTypeAnnotation(successor)]);
        } else if (successor)
          addMultipleAnnotations([convertToServerAnnotation(successor)]);
      } else {
        await drop({ variables });
      }
    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "Unable to save the review. Please try again."
      );
    }
  };

  return (
    <Review aria-label="Annotation version review">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        Carried-over annotations{count ? ` · ${count} stale` : ""}
      </button>
      {reviewPending && (
        <span role="status" aria-label="Annotation placement">
          Select the corrected passage on this document to save the review.
          <button type="button" onClick={() => setPending(null)}>
            Cancel placement
          </button>
        </span>
      )}
      {open && (
        <>
          <p>
            Review annotations from the previous version. Approve an exact
            match, place a corrected annotation, or drop one that no longer
            applies. Re-create any relationships between annotations after
            reviewing their endpoints.
          </p>
          {readOnly && (
            <p>
              Update permission on this document and corpus is required to
              review.
            </p>
          )}
          {loading && !data && <p role="status">Loading annotation review…</p>}
          {(error || message) && (
            <p role="alert">{message || "Unable to load annotation review."}</p>
          )}
          <div className="rows">
            {data?.annotationVersionReview.map((row) => (
              <article key={row.annotation.id}>
                <strong>
                  {row.annotation.annotationLabel?.text || "Annotation"}
                </strong>
                {" · "}
                <span>{VERSION_STATE_LABELS[row.state]}</span>
                <blockquote>{row.annotation.rawText}</blockquote>
                {row.state === "STALE" ? (
                  <>
                    {!row.proposedPlacement && (
                      <p>
                        No unique exact match. Place it on the new text or drop
                        it.
                      </p>
                    )}
                    <button
                      type="button"
                      disabled={readOnly || busy || !row.proposedPlacement}
                      onClick={() => void decide(row, true)}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={
                        readOnly ||
                        busy ||
                        !row.annotation.annotationLabel ||
                        row.annotation.annotationType === LabelType.DocTypeLabel
                      }
                      onClick={() => {
                        setPending({
                          annotationId: row.annotation.id,
                          documentId,
                          corpusId,
                          label: row.annotation.annotationLabel,
                        });
                        setLabel(row.annotation.annotationLabel);
                        setOpen(false);
                        onPlace();
                      }}
                    >
                      Place
                    </button>
                    <button
                      type="button"
                      disabled={readOnly || busy}
                      onClick={() => void decide(row, false)}
                    >
                      Drop
                    </button>
                  </>
                ) : (
                  <p>
                    {row.reviewedBy?.slug &&
                      `Reviewed by ${row.reviewedBy.slug}`}
                    {row.reviewedAt &&
                      ` · ${new Date(row.reviewedAt).toLocaleString()}`}
                  </p>
                )}
              </article>
            ))}
          </div>
          {data?.annotationVersionReview.length === 0 && (
            <p>No human annotations to review from the previous version.</p>
          )}
        </>
      )}
    </Review>
  );
}
