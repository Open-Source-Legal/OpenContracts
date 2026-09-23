import React, { useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import styled from "styled-components";
import { Check, History, X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  ANNOTATION_VERSION_STATES,
  ANNOTATION_VERSION_STATE_META,
} from "../../../assets/configurations/constants";
import {
  AnnotationVersionReviewEntry,
  GET_ANNOTATION_VERSION_REVIEW,
  GetAnnotationVersionReviewInput,
  GetAnnotationVersionReviewOutput,
} from "../../../graphql/queries";
import {
  CARRY_FORWARD_ANNOTATION,
  CarryForwardAnnotationInput,
  CarryForwardAnnotationOutput,
  DROP_STALE_ANNOTATION,
  DropStaleAnnotationInput,
  DropStaleAnnotationOutput,
} from "../../../graphql/mutations";
import { AnnotationVersionStateChip } from "../../annotator/display/components/AnnotationVersionStateChip";

/**
 * DocumentAnnotationReviewPanel — "Carried over" annotations.
 *
 * When a document gets a new version, every human annotation on the previous
 * version is **stale** relative to the new text until a reviewer decides:
 *
 *   • **Approve** — the exact text was found in the new version; create the
 *     successor annotation there (recorded as re-approved).
 *   • **Drop** — it no longer applies (recorded as dropped).
 *
 * Nothing is ever moved automatically: the previous version keeps its
 * annotations, and each decision is an auditable row. Entries without an
 * exact-text match cannot be approved here; re-annotate in the viewer and
 * drop the stale entry. Design: docs/architecture/reference-web-versioning.md.
 */

interface DocumentAnnotationReviewPanelProps {
  documentId: string;
  corpusId?: string;
}

const PanelBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 0.75rem 1rem 1.25rem;
`;

const Summary = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
  .stale {
    color: ${ANNOTATION_VERSION_STATE_META.STALE.color};
    font-weight: 600;
  }
  .dot {
    opacity: 0.6;
  }
`;

const SectionTitle = styled.div`
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 0.25rem;
`;

const List = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.5rem;
`;

const Row = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.6rem 0.75rem;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
`;

const RowHead = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
`;

const LabelChip = styled.span<{ $color: string }>`
  flex-shrink: 0;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 700;
  color: white;
  background: ${(p) => p.$color};
`;

const Snippet = styled.div`
  font-size: 0.8125rem;
  line-height: 1.4;
  color: ${OS_LEGAL_COLORS.textPrimary};
  overflow-wrap: anywhere;
`;

const Hint = styled.div`
  font-size: 0.6875rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const Actions = styled.div`
  display: flex;
  align-items: center;
  gap: 0.4rem;
`;

const ActionButton = styled.button<{ $primary?: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.7rem;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid
    ${(p) => (p.$primary ? "transparent" : OS_LEGAL_COLORS.border)};
  background: ${(p) => (p.$primary ? "#E8613D" : "white")};
  color: ${(p) => (p.$primary ? "white" : OS_LEGAL_COLORS.textSecondary)};
  transition: background 0.15s ease, border-color 0.15s ease;
  svg {
    width: 13px;
    height: 13px;
  }
  &:hover:not(:disabled) {
    background: ${(p) =>
      p.$primary ? "#D5522F" : OS_LEGAL_COLORS.surfaceHover};
    border-color: ${(p) =>
      p.$primary ? "transparent" : OS_LEGAL_COLORS.borderHover};
  }
  &:disabled {
    opacity: 0.55;
    cursor: default;
  }
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  padding: 2rem 1rem;
  text-align: center;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const ErrorText = styled.div`
  font-size: 0.75rem;
  color: ${ANNOTATION_VERSION_STATE_META.STALE.color};
`;

const STATE_ORDER = [
  ANNOTATION_VERSION_STATES.STALE,
  ANNOTATION_VERSION_STATES.CORRECTED,
  ANNOTATION_VERSION_STATES.REAPPROVED,
  ANNOTATION_VERSION_STATES.DROPPED,
] as const;

export const DocumentAnnotationReviewPanel: React.FC<
  DocumentAnnotationReviewPanelProps
> = ({ documentId, corpusId }) => {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});

  const variables: GetAnnotationVersionReviewInput = {
    documentId,
    corpusId: corpusId ?? null,
  };
  const { data, loading, error } = useQuery<
    GetAnnotationVersionReviewOutput,
    GetAnnotationVersionReviewInput
  >(GET_ANNOTATION_VERSION_REVIEW, { variables });

  const refetch = {
    refetchQueries: [{ query: GET_ANNOTATION_VERSION_REVIEW, variables }],
    awaitRefetchQueries: true,
  };
  const [carryForward] = useMutation<
    CarryForwardAnnotationOutput,
    CarryForwardAnnotationInput
  >(CARRY_FORWARD_ANNOTATION, refetch);
  const [dropStale] = useMutation<
    DropStaleAnnotationOutput,
    DropStaleAnnotationInput
  >(DROP_STALE_ANNOTATION, refetch);

  const entries = data?.annotationVersionReview ?? [];
  const staleCount = data?.document?.staleAnnotationCount ?? 0;

  const grouped = useMemo(() => {
    const byState = new Map<string, AnnotationVersionReviewEntry[]>();
    entries.forEach((e) => {
      const bucket = byState.get(e.state) ?? [];
      bucket.push(e);
      byState.set(e.state, bucket);
    });
    return STATE_ORDER.map((state) => ({
      state,
      items: byState.get(state) ?? [],
    })).filter((g) => g.items.length > 0);
  }, [entries]);

  const setError = (id: string, message?: string) =>
    setRowError((prev) => {
      const next = { ...prev };
      if (message) next[id] = message;
      else delete next[id];
      return next;
    });

  const onApprove = async (entry: AnnotationVersionReviewEntry) => {
    if (!entry.proposedJson || entry.proposedAnnotationType == null) return;
    setBusyId(entry.annotation.id);
    setError(entry.annotation.id);
    try {
      const res = await carryForward({
        variables: {
          annotationId: entry.annotation.id,
          targetDocumentId: documentId,
          json: entry.proposedJson,
          page: entry.proposedPage ?? 0,
          annotationType: entry.proposedAnnotationType,
          rawText: entry.proposedRawText ?? entry.annotation.rawText ?? "",
        },
      });
      const payload = res.data?.carryForwardAnnotation;
      if (!payload?.ok) {
        setError(entry.annotation.id, payload?.message || "Could not approve");
      }
    } catch (e) {
      setError(entry.annotation.id, (e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const onDrop = async (entry: AnnotationVersionReviewEntry) => {
    setBusyId(entry.annotation.id);
    setError(entry.annotation.id);
    try {
      const res = await dropStale({
        variables: {
          annotationId: entry.annotation.id,
          targetDocumentId: documentId,
        },
      });
      const payload = res.data?.dropStaleAnnotation;
      if (!payload?.ok) {
        setError(entry.annotation.id, payload?.message || "Could not drop");
      }
    } catch (e) {
      setError(entry.annotation.id, (e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  if (loading && entries.length === 0) {
    return (
      <PanelBody data-testid="annotation-review-loading">
        <Hint>Loading carried-over annotations…</Hint>
      </PanelBody>
    );
  }

  if (error && entries.length === 0) {
    return (
      <EmptyState data-testid="annotation-review-error">
        Couldn't load carried-over annotations. Please try again.
      </EmptyState>
    );
  }

  if (entries.length === 0) {
    return (
      <EmptyState data-testid="annotation-review-empty">
        <History size={18} style={{ color: OS_LEGAL_COLORS.textMuted }} />
        <div>
          Nothing carried over — this is either the first version of the
          document or its previous version had no annotations.
        </div>
      </EmptyState>
    );
  }

  const decidedCount = entries.length - staleCount;

  return (
    <PanelBody data-testid="annotation-review-panel">
      <Summary data-testid="annotation-review-summary">
        {staleCount > 0 ? (
          <span className="stale">
            {staleCount} stale {staleCount === 1 ? "annotation" : "annotations"}
          </span>
        ) : (
          <span>All carried-over annotations reviewed</span>
        )}
        {decidedCount > 0 && (
          <>
            <span className="dot">·</span>
            <span>{decidedCount} reviewed</span>
          </>
        )}
      </Summary>

      {grouped.map((group) => (
        <div key={group.state}>
          <SectionTitle>
            {ANNOTATION_VERSION_STATE_META[group.state].label}
          </SectionTitle>
          <List>
            {group.items.map((entry) => {
              const id = entry.annotation.id;
              const isStale = entry.state === ANNOTATION_VERSION_STATES.STALE;
              const canApprove = isStale && Boolean(entry.proposedJson);
              const busy = busyId === id;
              return (
                <Row
                  key={id}
                  data-testid="annotation-review-row"
                  data-state={entry.state}
                >
                  <RowHead>
                    {entry.annotation.annotationLabel?.text && (
                      <LabelChip
                        $color={
                          entry.annotation.annotationLabel.color ||
                          OS_LEGAL_COLORS.textSecondary
                        }
                      >
                        {entry.annotation.annotationLabel.text}
                      </LabelChip>
                    )}
                    <AnnotationVersionStateChip state={entry.state} />
                  </RowHead>
                  {entry.annotation.rawText && (
                    <Snippet>{entry.annotation.rawText}</Snippet>
                  )}
                  {isStale && (
                    <>
                      {canApprove ? (
                        <Hint>Exact text found in this version.</Hint>
                      ) : (
                        <Hint>
                          No exact match in this version — re-annotate in the
                          viewer, then drop this entry.
                        </Hint>
                      )}
                      <Actions>
                        {canApprove && (
                          <ActionButton
                            $primary
                            disabled={busy}
                            onClick={() => void onApprove(entry)}
                            data-testid="annotation-review-approve"
                          >
                            <Check />
                            Approve
                          </ActionButton>
                        )}
                        <ActionButton
                          disabled={busy}
                          onClick={() => void onDrop(entry)}
                          data-testid="annotation-review-drop"
                        >
                          <X />
                          Drop
                        </ActionButton>
                      </Actions>
                      {rowError[id] && <ErrorText>{rowError[id]}</ErrorText>}
                    </>
                  )}
                </Row>
              );
            })}
          </List>
        </div>
      ))}
    </PanelBody>
  );
};
