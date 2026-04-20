import React, { useState, useMemo, useCallback, useEffect } from "react";
import { Dropdown, DropdownOption } from "@os-legal/ui";
import styled from "styled-components";
import { useMutation, useQuery } from "@apollo/client";
import { toast } from "react-toastify";
import {
  Link2,
  FileText,
  X,
  Plus,
  Search,
  ArrowRight,
  ArrowLeft,
  Target,
} from "lucide-react";
import {
  Input,
  Button,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Textarea,
} from "@os-legal/ui";

import { useCorpusState } from "../annotator/context/CorpusAtom";
import { LabelType, DocumentType } from "../../types/graphql-api";
import {
  SMART_LABEL_SEARCH_OR_CREATE,
  SmartLabelSearchOrCreateInputs,
  SmartLabelSearchOrCreateOutputs,
  CREATE_DOCUMENT_RELATIONSHIP,
  CreateDocumentRelationshipInputs,
  CreateDocumentRelationshipOutputs,
} from "../../graphql/mutations";
import {
  GET_DOCUMENTS,
  RequestDocumentsOutputs,
  GET_DOCUMENT_RELATIONSHIPS,
} from "../../graphql/queries";
import {
  DOCUMENT_PICKER_SEARCH_LIMIT,
  MUTATION_BATCH_SIZE,
  DEBOUNCE,
} from "../../assets/configurations/constants";
import { ErrorMessage, WarningMessage } from "../widgets/feedback";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

// ============================================================================
// HELPERS
// ============================================================================

type LabelLike = {
  id: string;
  text?: string | null;
  labelType?: string | null;
};

/**
 * Filter a list of labels down to relationship-typed labels that match
 * `searchTerm`. When `hasCorpus` is false, returns an empty array (relationship
 * labels only make sense inside a corpus). An empty `searchTerm` returns all
 * relationship labels unfiltered. Case-insensitive substring match on `text`.
 */
export function filterRelationshipLabels<T extends LabelLike>(
  labels: T[] | null | undefined,
  searchTerm: string,
  hasCorpus: boolean
): T[] {
  if (!hasCorpus) return [];
  const relationshipOnly =
    labels?.filter(
      (label) => label.labelType === LabelType.RelationshipLabel
    ) || [];
  if (!searchTerm) return relationshipOnly;
  const needle = searchTerm.toLowerCase();
  return relationshipOnly.filter((label) =>
    (label.text ?? "").toLowerCase().includes(needle)
  );
}

// ============================================================================
// TYPES
// ============================================================================

interface DocumentInfo {
  id: string;
  title: string;
  icon?: string;
}

interface DocumentRelationshipModalProps {
  open: boolean;
  onClose: () => void;
  corpusId: string;
  /** Initial documents to place in source column (can be moved to target) */
  initialSourceIds?: string[];
  /** Initial documents to place in target column (can be moved to source) */
  initialTargetIds?: string[];
  onSuccess?: () => void;
}

type RelationshipMode = "RELATIONSHIP" | "NOTES";

// ============================================================================
// STYLED COMPONENTS
// ============================================================================

const StyledModalWrapper = styled.div``;

const ScrollableContent = styled.div`
  max-height: 70vh;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 8px;
  }
  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 4px;
    &:hover {
      background: ${OS_LEGAL_COLORS.textMuted};
    }
  }
`;

const ModeSection = styled.div`
  margin-bottom: 1.5rem;
  padding: 1rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  background: ${OS_LEGAL_COLORS.background};
`;

const DocumentPill = styled.div<{ $variant?: "source" | "target" }>`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  margin: 0.25rem;
  border-radius: 6px;
  font-size: 0.875rem;
  background: ${(props) =>
    props.$variant === "source"
      ? OS_LEGAL_COLORS.blueBorder
      : OS_LEGAL_COLORS.successBorder};
  border: 2px solid
    ${(props) =>
      props.$variant === "source"
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.green};
  color: ${(props) =>
    props.$variant === "source"
      ? OS_LEGAL_COLORS.blueDark
      : OS_LEGAL_COLORS.successText};
`;

const PillButton = styled.button`
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: inherit;
  opacity: 0.6;
  transition: opacity 0.15s;
  border-radius: 4px;

  &:hover {
    opacity: 1;
    background: rgba(0, 0, 0, 0.1);
  }
`;

const TwoColumnLayout = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-top: 1rem;

  @media (max-width: 600px) {
    grid-template-columns: 1fr;
  }
`;

const ColumnHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;

  .column-title {
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
  }

  .column-count {
    font-size: 0.75rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
    background: ${OS_LEGAL_COLORS.surfaceLight};
    padding: 2px 8px;
    border-radius: 10px;
  }
`;

const DocumentSection = styled.div`
  margin-top: 1rem;
  padding: 1rem;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;

  .section-title {
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .pills-container {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    min-height: 40px;
    padding: 0.5rem;
    background: ${OS_LEGAL_COLORS.background};
    border-radius: 4px;
  }
`;

const SearchResultItem = styled.div<{ $selected: boolean }>`
  padding: 0.75rem;
  margin: 0.25rem 0;
  border: 1px solid
    ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  background: ${(props) =>
    props.$selected ? OS_LEGAL_COLORS.blueSurface : "white"};
  display: flex;
  align-items: center;
  gap: 0.75rem;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  .doc-icon {
    flex-shrink: 0;
  }

  .doc-info {
    flex: 1;
    min-width: 0;

    .doc-title {
      font-weight: 500;
      color: ${OS_LEGAL_COLORS.textPrimary};
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 2rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-style: italic;
`;

const InfoBox = styled.div`
  margin-top: 1rem;
  padding: 0.75rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 6px;
  border-left: 4px solid ${OS_LEGAL_COLORS.primaryBlue};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

// ============================================================================
// COMPONENT
// ============================================================================

export const DocumentRelationshipModal: React.FC<
  DocumentRelationshipModalProps
> = ({
  open,
  onClose,
  corpusId,
  initialSourceIds = [],
  initialTargetIds = [],
  onSuccess,
}) => {
  const { relationLabels, selectedCorpus, setCorpus } = useCorpusState();

  // Mode state
  const [mode, setMode] = useState<RelationshipMode>("RELATIONSHIP");

  // Source and target document IDs (can be moved between lists)
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [targetIds, setTargetIds] = useState<string[]>([]);

  // Document search for adding more documents
  const [documentSearchTerm, setDocumentSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [addingToSide, setAddingToSide] = useState<"source" | "target" | null>(
    null
  );

  // Label selection (for RELATIONSHIP mode)
  const [selectedLabelId, setSelectedLabelId] = useState<string | null>(null);
  const [labelSearchTerm, setLabelSearchTerm] = useState("");
  const [showCreateLabel, setShowCreateLabel] = useState(false);
  const [newLabelText, setNewLabelText] = useState("");
  const [newLabelColor, setNewLabelColor] = useState<string>(
    OS_LEGAL_COLORS.greenMedium
  );
  const [newLabelDescription, setNewLabelDescription] = useState("");

  // Notes data (for NOTES mode)
  const [notesContent, setNotesContent] = useState("");

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Initialize source/target IDs when modal opens
  useEffect(() => {
    if (open) {
      setSourceIds(initialSourceIds);
      setTargetIds(initialTargetIds);
    }
  }, [open, initialSourceIds, initialTargetIds]);

  // Check if we have corpus context
  const hasCorpus = Boolean(corpusId && selectedCorpus?.id);
  const hasLabelset = Boolean(selectedCorpus?.labelSet);

  // Debounce search term to avoid excessive queries
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(documentSearchTerm);
    }, DEBOUNCE.SEARCH_MS);

    return () => clearTimeout(timer);
  }, [documentSearchTerm]);

  // Query for documents in corpus (for target selection).
  // NOTE(perf): Source documents are excluded client-side in availableDocuments
  // memo below. An `excludeIds` backend parameter could improve performance at
  // scale but is not critical for typical corpus sizes.
  const { data: documentsData, loading: documentsLoading } =
    useQuery<RequestDocumentsOutputs>(GET_DOCUMENTS, {
      variables: {
        inCorpusWithId: corpusId,
        textSearch: debouncedSearchTerm || undefined,
        limit: DOCUMENT_PICKER_SEARCH_LIMIT,
        annotateDocLabels: false,
        includeMetadata: false,
        includeCaml: false,
      },
      skip: !open || !corpusId,
      fetchPolicy: "cache-and-network",
    });

  // Mutations
  const [smartLabelSearchOrCreate] = useMutation<
    SmartLabelSearchOrCreateOutputs,
    SmartLabelSearchOrCreateInputs
  >(SMART_LABEL_SEARCH_OR_CREATE);

  const [createDocumentRelationship] = useMutation<
    CreateDocumentRelationshipOutputs,
    CreateDocumentRelationshipInputs
  >(CREATE_DOCUMENT_RELATIONSHIP);

  // All documents from query
  const allDocuments = useMemo(() => {
    return (
      documentsData?.documents?.edges
        ?.map((e) => e?.node)
        .filter(
          (doc): doc is NonNullable<typeof doc> => doc != null && doc.id != null
        ) || []
    );
  }, [documentsData]);

  // Get source documents with info from query results
  const sourceDocuments = useMemo(() => {
    return allDocuments
      .filter((doc) => sourceIds.includes(doc.id))
      .map((doc) => ({
        id: doc.id,
        title: doc.title || "Untitled",
        icon: doc.icon || undefined,
      }));
  }, [allDocuments, sourceIds]);

  // Get target documents with info from query results
  const targetDocuments = useMemo(() => {
    return allDocuments
      .filter((doc) => targetIds.includes(doc.id))
      .map((doc) => ({
        id: doc.id,
        title: doc.title || "Untitled",
        icon: doc.icon || undefined,
      }));
  }, [allDocuments, targetIds]);

  // Get available documents (excluding already selected source and target)
  const availableDocuments = useMemo(() => {
    const usedIds = new Set([...sourceIds, ...targetIds]);
    return allDocuments.filter((doc) => !usedIds.has(doc.id));
  }, [allDocuments, sourceIds, targetIds]);

  // Manual filter keeps `labelSearchTerm` in sync — @os-legal/ui's Dropdown only fires `onSearchChange` in `async` mode.
  const filteredRelationshipLabels = useMemo(
    () => filterRelationshipLabels(relationLabels, labelSearchTerm, hasCorpus),
    [relationLabels, hasCorpus, labelSearchTerm]
  );

  // Get selected label info
  const selectedLabel = useMemo(() => {
    if (!selectedLabelId) return null;
    return relationLabels?.find((l) => l.id === selectedLabelId);
  }, [selectedLabelId, relationLabels]);

  // Handle creating a new relationship label
  const handleCreateLabel = useCallback(async () => {
    if (!hasCorpus) {
      toast.error("Cannot create labels without a selected corpus");
      return;
    }

    if (!newLabelText.trim()) {
      toast.error("Please enter a label name");
      return;
    }

    try {
      const result = await smartLabelSearchOrCreate({
        variables: {
          corpusId,
          searchTerm: newLabelText,
          labelType: LabelType.RelationshipLabel,
          color: newLabelColor,
          description: newLabelDescription,
          createIfNotFound: true,
        },
      });

      if (result.data?.smartLabelSearchOrCreate?.ok) {
        const { labels, labelsetCreated, labelCreated } =
          result.data.smartLabelSearchOrCreate;

        if (labels && labels.length > 0) {
          const newLabel = labels[0];

          // Update corpus state with new label
          if (labelCreated) {
            setCorpus({
              relationLabels: [...(relationLabels || []), newLabel],
            });
          }

          // Select the new label
          setSelectedLabelId(newLabel.id);
          setShowCreateLabel(false);
          setLabelSearchTerm("");
          setNewLabelText("");
          setNewLabelDescription("");

          if (labelsetCreated) {
            toast.success(`Created labelset and label "${newLabelText}"`);
          } else if (labelCreated) {
            toast.success(`Created label "${newLabelText}"`);
          } else {
            toast.info(`Selected existing label "${newLabelText}"`);
          }
        }
      } else {
        toast.error(
          result.data?.smartLabelSearchOrCreate?.message ||
            "Failed to create label"
        );
      }
    } catch (error) {
      console.error("Error creating relationship label:", error);
      toast.error("Failed to create label");
    }
  }, [
    hasCorpus,
    corpusId,
    newLabelText,
    newLabelColor,
    newLabelDescription,
    smartLabelSearchOrCreate,
    relationLabels,
    setCorpus,
  ]);

  // Move document from source to target
  const moveToTarget = useCallback((docId: string) => {
    setSourceIds((prev) => prev.filter((id) => id !== docId));
    setTargetIds((prev) => [...prev, docId]);
  }, []);

  // Move document from target to source
  const moveToSource = useCallback((docId: string) => {
    setTargetIds((prev) => prev.filter((id) => id !== docId));
    setSourceIds((prev) => [...prev, docId]);
  }, []);

  // Remove document from source
  const removeFromSource = useCallback((docId: string) => {
    setSourceIds((prev) => prev.filter((id) => id !== docId));
  }, []);

  // Remove document from target
  const removeFromTarget = useCallback((docId: string) => {
    setTargetIds((prev) => prev.filter((id) => id !== docId));
  }, []);

  // Add document to source or target
  const addDocument = useCallback(
    (docId: string, side: "source" | "target") => {
      if (side === "source") {
        setSourceIds((prev) => [...prev, docId]);
      } else {
        setTargetIds((prev) => [...prev, docId]);
      }
      setAddingToSide(null);
      setDocumentSearchTerm("");
    },
    []
  );

  // Check if form is valid
  const canSubmit = useMemo(() => {
    // Need at least one source and one target
    if (sourceIds.length === 0) return false;
    if (targetIds.length === 0) return false;
    if (mode === "RELATIONSHIP" && !selectedLabelId) return false;
    return true;
  }, [sourceIds.length, targetIds.length, mode, selectedLabelId]);

  // Handle form submission with batched mutations
  const handleSubmit = async () => {
    if (!canSubmit) return;

    setIsSubmitting(true);

    try {
      // Build all mutation configs
      const mutations = sourceIds.flatMap((sourceId) =>
        targetIds.map((targetId) => ({
          sourceId,
          targetId,
          variables: {
            sourceDocumentId: sourceId,
            targetDocumentId: targetId,
            relationshipType: mode,
            corpusId,
            annotationLabelId:
              mode === "RELATIONSHIP"
                ? selectedLabelId ?? undefined
                : undefined,
            data:
              mode === "NOTES" && notesContent
                ? { notes: notesContent }
                : undefined,
          },
        }))
      );

      const totalCount = mutations.length;
      let successCount = 0;
      const failures: Array<{
        sourceId: string;
        targetId: string;
        error: string;
      }> = [];

      // Process mutations in batches to avoid overwhelming the server
      for (let i = 0; i < mutations.length; i += MUTATION_BATCH_SIZE) {
        const batch = mutations.slice(i, i + MUTATION_BATCH_SIZE);
        const batchPromises = batch.map((mutation) =>
          createDocumentRelationship({
            variables: mutation.variables,
            // Only refetch on the last batch to avoid excessive refetches
            refetchQueries:
              i + MUTATION_BATCH_SIZE >= mutations.length
                ? [
                    {
                      query: GET_DOCUMENT_RELATIONSHIPS,
                      variables: { corpusId },
                    },
                  ]
                : [],
          })
            .then((result) => ({
              mutation,
              result,
              success: result.data?.createDocumentRelationship?.ok ?? false,
              error: result.data?.createDocumentRelationship?.message,
            }))
            .catch((err) => ({
              mutation,
              result: null,
              success: false,
              error: err instanceof Error ? err.message : "Network error",
            }))
        );

        const batchResults = await Promise.allSettled(batchPromises);

        // Process batch results
        batchResults.forEach((settledResult) => {
          if (settledResult.status === "fulfilled") {
            const { mutation, success, error } = settledResult.value;
            if (success) {
              successCount++;
            } else {
              failures.push({
                sourceId: mutation.sourceId,
                targetId: mutation.targetId,
                error: error || "Unknown error",
              });
            }
          } else {
            // Promise rejected (shouldn't happen with our .catch, but handle it)
            failures.push({
              sourceId: "unknown",
              targetId: "unknown",
              error: settledResult.reason?.message || "Unknown error",
            });
          }
        });
      }

      // Report results with detailed error information
      if (successCount === totalCount) {
        toast.success(
          `Created ${successCount} document relationship${
            successCount > 1 ? "s" : ""
          }`
        );
        onSuccess?.();
        handleClose();
      } else if (successCount > 0) {
        const uniqueErrors = [...new Set(failures.map((f) => f.error))];
        const errorSummary =
          uniqueErrors.length === 1
            ? uniqueErrors[0]
            : `${uniqueErrors.length} different errors`;
        toast.warning(
          `Created ${successCount} of ${totalCount} relationships. Failed: ${failures.length} (${errorSummary})`
        );
        onSuccess?.();
        handleClose();
      } else {
        const uniqueErrors = [...new Set(failures.map((f) => f.error))];
        const errorMsg =
          uniqueErrors.length === 1
            ? uniqueErrors[0]
            : `Multiple errors: ${uniqueErrors.slice(0, 3).join(", ")}${
                uniqueErrors.length > 3 ? "..." : ""
              }`;
        toast.error(`Failed to create relationships: ${errorMsg}`);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown error occurred";
      toast.error(`Failed to create relationships: ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Reset state on close
  const handleClose = () => {
    setMode("RELATIONSHIP");
    setSourceIds([]);
    setTargetIds([]);
    setDocumentSearchTerm("");
    setDebouncedSearchTerm("");
    setAddingToSide(null);
    setSelectedLabelId(null);
    setLabelSearchTerm("");
    setShowCreateLabel(false);
    setNewLabelText("");
    setNewLabelColor(OS_LEGAL_COLORS.greenMedium);
    setNewLabelDescription("");
    setNotesContent("");
    onClose();
  };

  return (
    <StyledModalWrapper>
      <Modal open={open} onClose={handleClose} size="md">
        <ModalHeader>
          <div style={{ display: "flex", alignItems: "center" }}>
            <Link2 size={20} style={{ marginRight: "0.5rem" }} />
            Link Documents
          </div>
        </ModalHeader>
        <ModalBody>
          <ScrollableContent>
            {!hasCorpus && (
              <ErrorMessage
                title="No Corpus Context"
                style={{ marginBottom: "1.5rem" }}
              >
                Document relationships require a corpus context.
              </ErrorMessage>
            )}

            {/* Two-Column Source/Target Layout */}
            <TwoColumnLayout>
              {/* Source Documents Column */}
              <DocumentSection>
                <ColumnHeader>
                  <div className="column-title">
                    <ArrowRight size={14} color={OS_LEGAL_COLORS.primaryBlue} />
                    Source Documents
                  </div>
                  <span className="column-count">{sourceIds.length}</span>
                </ColumnHeader>
                <div className="pills-container">
                  {sourceDocuments.length > 0 ? (
                    sourceDocuments.map((doc) => (
                      <DocumentPill key={doc.id} $variant="source">
                        <FileText size={14} />
                        <span title={doc.title}>
                          {doc.title.length > 20
                            ? `${doc.title.substring(0, 20)}...`
                            : doc.title}
                        </span>
                        <PillButton
                          onClick={() => moveToTarget(doc.id)}
                          title="Move to targets"
                        >
                          <ArrowRight size={12} />
                        </PillButton>
                        <PillButton
                          onClick={() => removeFromSource(doc.id)}
                          title="Remove"
                        >
                          <X size={12} />
                        </PillButton>
                      </DocumentPill>
                    ))
                  ) : documentsLoading ? (
                    <span
                      style={{
                        color: OS_LEGAL_COLORS.textSecondary,
                        fontStyle: "italic",
                      }}
                    >
                      Loading...
                    </span>
                  ) : (
                    <span
                      style={{
                        color: OS_LEGAL_COLORS.textSecondary,
                        fontStyle: "italic",
                      }}
                    >
                      No source documents
                    </span>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  leftIcon={
                    addingToSide === "source" ? (
                      <X size={14} />
                    ) : (
                      <Plus size={14} />
                    )
                  }
                  onClick={() =>
                    setAddingToSide(addingToSide === "source" ? null : "source")
                  }
                  style={{ marginTop: "0.5rem" }}
                >
                  {addingToSide === "source" ? "Cancel" : "Add Source"}
                </Button>
              </DocumentSection>

              {/* Target Documents Column */}
              <DocumentSection>
                <ColumnHeader>
                  <div className="column-title">
                    <Target size={14} color={OS_LEGAL_COLORS.green} />
                    Target Documents
                  </div>
                  <span className="column-count">{targetIds.length}</span>
                </ColumnHeader>
                <div className="pills-container">
                  {targetDocuments.length > 0 ? (
                    targetDocuments.map((doc) => (
                      <DocumentPill key={doc.id} $variant="target">
                        <PillButton
                          onClick={() => moveToSource(doc.id)}
                          title="Move to sources"
                        >
                          <ArrowLeft size={12} />
                        </PillButton>
                        <FileText size={14} />
                        <span title={doc.title}>
                          {doc.title.length > 20
                            ? `${doc.title.substring(0, 20)}...`
                            : doc.title}
                        </span>
                        <PillButton
                          onClick={() => removeFromTarget(doc.id)}
                          title="Remove"
                        >
                          <X size={12} />
                        </PillButton>
                      </DocumentPill>
                    ))
                  ) : (
                    <span
                      style={{
                        color: OS_LEGAL_COLORS.textSecondary,
                        fontStyle: "italic",
                      }}
                    >
                      No target documents
                    </span>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  leftIcon={
                    addingToSide === "target" ? (
                      <X size={14} />
                    ) : (
                      <Plus size={14} />
                    )
                  }
                  onClick={() =>
                    setAddingToSide(addingToSide === "target" ? null : "target")
                  }
                  style={{ marginTop: "0.5rem" }}
                >
                  {addingToSide === "target" ? "Cancel" : "Add Target"}
                </Button>
              </DocumentSection>
            </TwoColumnLayout>

            {/* Document Search (when adding) */}
            {addingToSide && (
              <DocumentSection style={{ marginTop: "1rem" }}>
                <div className="section-title">
                  <Search size={16} />
                  Add to {addingToSide === "source" ? "Sources" : "Targets"}
                </div>
                <div>
                  <Input
                    fullWidth
                    placeholder="Search documents in corpus..."
                    value={documentSearchTerm}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setDocumentSearchTerm(e.target.value)
                    }
                    autoFocus
                  />
                </div>
                <div
                  style={{
                    maxHeight: "150px",
                    overflowY: "auto",
                    marginTop: "0.5rem",
                  }}
                >
                  {documentsLoading ? (
                    <EmptyState>Loading documents...</EmptyState>
                  ) : availableDocuments.length > 0 ? (
                    availableDocuments.slice(0, 10).map((doc) => (
                      <SearchResultItem
                        key={doc.id}
                        $selected={false}
                        onClick={() => addDocument(doc.id, addingToSide)}
                      >
                        <div className="doc-icon">
                          <FileText
                            size={16}
                            color={OS_LEGAL_COLORS.textSecondary}
                          />
                        </div>
                        <div className="doc-info">
                          <div className="doc-title">{doc.title}</div>
                        </div>
                        <Plus size={16} color={OS_LEGAL_COLORS.textSecondary} />
                      </SearchResultItem>
                    ))
                  ) : (
                    <EmptyState>
                      {documentSearchTerm
                        ? "No documents found"
                        : "No available documents"}
                    </EmptyState>
                  )}
                </div>
              </DocumentSection>
            )}

            {/* Relationship Type Selection */}
            <ModeSection style={{ marginTop: "1rem" }}>
              <div>
                <label
                  style={{
                    fontWeight: 600,
                    marginBottom: "0.5rem",
                    display: "block",
                  }}
                >
                  Relationship Type
                </label>
                <div
                  style={{
                    display: "flex",
                    gap: "1.5rem",
                    marginTop: "0.5rem",
                  }}
                >
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      cursor: hasCorpus ? "pointer" : "default",
                      opacity: hasCorpus ? 1 : 0.5,
                    }}
                  >
                    <input
                      type="radio"
                      name="relationship-mode"
                      value="RELATIONSHIP"
                      checked={mode === "RELATIONSHIP"}
                      onChange={() => setMode("RELATIONSHIP")}
                      disabled={!hasCorpus}
                    />
                    Labeled Relationship
                  </label>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      cursor: hasCorpus ? "pointer" : "default",
                      opacity: hasCorpus ? 1 : 0.5,
                    }}
                  >
                    <input
                      type="radio"
                      name="relationship-mode"
                      value="NOTES"
                      checked={mode === "NOTES"}
                      onChange={() => setMode("NOTES")}
                      disabled={!hasCorpus}
                    />
                    Notes
                  </label>
                </div>
              </div>

              {/* Label Selection (for RELATIONSHIP mode) */}
              {mode === "RELATIONSHIP" && (
                <>
                  {!hasLabelset && (
                    <WarningMessage style={{ marginTop: "1rem" }}>
                      <strong>No labelset found.</strong> Creating a label will
                      automatically create a labelset for this corpus.
                    </WarningMessage>
                  )}

                  {!selectedLabel ? (
                    !showCreateLabel ? (
                      <div style={{ marginTop: "1rem" }}>
                        <label
                          style={{
                            display: "block",
                            fontWeight: 600,
                            marginBottom: "0.5rem",
                          }}
                        >
                          Relationship Label
                        </label>
                        <Dropdown
                          mode="select"
                          placeholder="Search or type to create..."
                          fluid
                          searchable="async"
                          options={filteredRelationshipLabels.map((label) => ({
                            value: label.id,
                            label: label.text || "",
                          }))}
                          renderOption={(option) => (
                            <span
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.5rem",
                              }}
                            >
                              <span
                                style={{
                                  width: 10,
                                  height: 10,
                                  borderRadius: 2,
                                  backgroundColor:
                                    filteredRelationshipLabels.find(
                                      (l) => l.id === option.value
                                    )?.color || OS_LEGAL_COLORS.greenMedium,
                                  flexShrink: 0,
                                }}
                              />
                              {option.label}
                            </span>
                          )}
                          renderEmpty={() =>
                            labelSearchTerm ? (
                              <button
                                type="button"
                                style={{
                                  cursor: "pointer",
                                  color: OS_LEGAL_COLORS.primaryBlue,
                                  padding: "0.25rem 0.5rem",
                                  display: "block",
                                  width: "100%",
                                  textAlign: "left",
                                  background: "none",
                                  border: "none",
                                  font: "inherit",
                                }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setNewLabelText(labelSearchTerm);
                                  setShowCreateLabel(true);
                                }}
                              >
                                Create label: &ldquo;{labelSearchTerm}&rdquo;
                              </button>
                            ) : (
                              <span
                                style={{
                                  color: OS_LEGAL_COLORS.textSecondary,
                                  padding: "0.25rem 0",
                                  display: "block",
                                }}
                              >
                                Type to create a new label
                              </span>
                            )
                          }
                          value={selectedLabelId ?? null}
                          onSearchChange={(query) => setLabelSearchTerm(query)}
                          onChange={(value) => {
                            setSelectedLabelId(value as string);
                          }}
                        />
                      </div>
                    ) : (
                      <>
                        <div style={{ marginTop: "1rem" }}>
                          <label
                            style={{
                              display: "block",
                              fontWeight: 600,
                              marginBottom: "0.5rem",
                            }}
                          >
                            Create New Label
                          </label>
                          <Input
                            fullWidth
                            placeholder="Enter label name"
                            value={newLabelText}
                            onChange={(
                              e: React.ChangeEvent<HTMLInputElement>
                            ) => setNewLabelText(e.target.value)}
                            autoFocus
                          />
                        </div>

                        <div
                          style={{
                            display: "flex",
                            gap: "1rem",
                            marginTop: "0.75rem",
                          }}
                        >
                          <div>
                            <label
                              style={{
                                display: "block",
                                fontWeight: 600,
                                marginBottom: "0.5rem",
                              }}
                            >
                              Color
                            </label>
                            <input
                              type="color"
                              value={newLabelColor}
                              onChange={(e) => setNewLabelColor(e.target.value)}
                              style={{ width: "60px", padding: "2px" }}
                            />
                          </div>

                          <div style={{ flex: 1 }}>
                            <label
                              style={{
                                display: "block",
                                fontWeight: 600,
                                marginBottom: "0.5rem",
                              }}
                            >
                              Description (optional)
                            </label>
                            <Input
                              fullWidth
                              placeholder="Enter description"
                              value={newLabelDescription}
                              onChange={(
                                e: React.ChangeEvent<HTMLInputElement>
                              ) => setNewLabelDescription(e.target.value)}
                            />
                          </div>
                        </div>

                        <div
                          style={{
                            display: "flex",
                            gap: "0.5rem",
                            marginTop: "0.5rem",
                          }}
                        >
                          <Button
                            variant="secondary"
                            onClick={() => {
                              setShowCreateLabel(false);
                              setNewLabelText("");
                              setNewLabelDescription("");
                            }}
                            style={{ flex: 1 }}
                          >
                            Cancel
                          </Button>
                          <Button
                            variant="primary"
                            onClick={handleCreateLabel}
                            style={{ flex: 1 }}
                          >
                            Create Label
                          </Button>
                        </div>
                      </>
                    )
                  ) : (
                    <div style={{ marginTop: "1rem" }}>
                      <label
                        style={{
                          display: "block",
                          fontWeight: 600,
                          marginBottom: "0.5rem",
                        }}
                      >
                        Selected Label
                      </label>
                      <div
                        style={{
                          padding: "0.75rem",
                          background: OS_LEGAL_COLORS.surfaceHover,
                          border: `1px solid ${OS_LEGAL_COLORS.border}`,
                          borderRadius: "6px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 500,
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                          }}
                        >
                          <span
                            style={{
                              width: 12,
                              height: 12,
                              borderRadius: 3,
                              backgroundColor:
                                selectedLabel.color ||
                                OS_LEGAL_COLORS.greenMedium,
                            }}
                          />
                          {selectedLabel.text}
                        </span>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setSelectedLabelId(null);
                            setLabelSearchTerm("");
                          }}
                        >
                          Change
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Notes Content (for NOTES mode) */}
              {mode === "NOTES" && (
                <div style={{ marginTop: "1rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontWeight: 600,
                      marginBottom: "0.5rem",
                    }}
                  >
                    Notes (optional)
                  </label>
                  <Textarea
                    placeholder="Add notes about this document relationship..."
                    value={notesContent}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                      setNotesContent(e.target.value)
                    }
                    rows={3}
                  />
                </div>
              )}
            </ModeSection>

            <InfoBox>
              <strong>
                Creating {sourceIds.length * targetIds.length} relationship
                {sourceIds.length * targetIds.length !== 1 ? "s" : ""}
              </strong>
              : Each source document will be linked to each target document.
              {sourceIds.length === 0 && (
                <span
                  style={{
                    color: OS_LEGAL_COLORS.danger,
                    display: "block",
                    marginTop: 4,
                  }}
                >
                  ⚠ Add at least one source document
                </span>
              )}
              {targetIds.length === 0 && (
                <span
                  style={{
                    color: OS_LEGAL_COLORS.danger,
                    display: "block",
                    marginTop: 4,
                  }}
                >
                  ⚠ Add at least one target document
                </span>
              )}
            </InfoBox>
          </ScrollableContent>
        </ModalBody>

        <ModalFooter>
          <Button
            variant="secondary"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!hasCorpus || !canSubmit || isSubmitting}
            loading={isSubmitting}
            leftIcon={<Link2 size={16} />}
          >
            Create Relationship
            {sourceIds.length * targetIds.length !== 1 ? "s" : ""}
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};

export default DocumentRelationshipModal;
