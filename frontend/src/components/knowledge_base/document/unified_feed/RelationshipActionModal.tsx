import React, { useState, useMemo } from "react";
import {
  Button,
  Dropdown,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";
import {
  ArrowRight,
  Target,
  Check,
  Info,
  Plus,
  Search,
  Link,
} from "lucide-react";
import { DynamicIcon } from "../../../widgets/icon-picker/DynamicIcon";
import styled from "styled-components";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { RelationGroup } from "../../../annotator/types/annotations";
import { useCorpusState } from "../../../annotator/context/CorpusAtom";
import { LabelType } from "../../../../types/graphql-api";
import {
  SMART_LABEL_SEARCH_OR_CREATE,
  SmartLabelSearchOrCreateInputs,
  SmartLabelSearchOrCreateOutputs,
} from "../../../../graphql/mutations";
import { ErrorMessage, WarningMessage } from "../../../widgets/feedback";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

interface RelationshipActionModalProps {
  open: boolean;
  onClose: () => void;
  selectedAnnotationIds: string[];
  existingRelationships: RelationGroup[];
  corpusId: string;
  documentId: string;
  annotations?: Array<{ id: string; rawText?: string }>;
  onAddToExisting: (
    relationshipId: string,
    role: "source" | "target"
  ) => Promise<void>;
  onCreate: (
    labelId: string,
    sourceIds: string[],
    targetIds: string[]
  ) => Promise<void>;
}

const ScrollableContent = styled.div`
  max-height: 60vh;
  overflow-y: auto;
  padding: 1rem;

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

const RelationshipOption = styled.div<{ $selected: boolean }>`
  padding: 1rem;
  margin: 0.5rem 0;
  border: 2px solid
    ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background: ${(props) =>
    props.$selected ? OS_LEGAL_COLORS.blueSurface : "white"};

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  .relationship-label {
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
    margin-bottom: 0.25rem;
  }

  .relationship-stats {
    font-size: 0.875rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
    display: flex;
    gap: 1rem;
  }
`;

const InfoBox = styled.div`
  margin-top: 1rem;
  padding: 0.75rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 6px;
  border-left: 4px solid ${OS_LEGAL_COLORS.primaryBlue};

  strong {
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const ModeSection = styled.div`
  margin-bottom: 1.5rem;
  padding: 1rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  background: ${OS_LEGAL_COLORS.background};
`;

const AnnotationPill = styled.div<{
  $role: "source" | "target" | "unassigned";
}>`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  margin: 0.25rem;
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
  background: ${(props) =>
    props.$role === "source"
      ? OS_LEGAL_COLORS.blueBorder
      : props.$role === "target"
        ? OS_LEGAL_COLORS.successSurface
        : OS_LEGAL_COLORS.surfaceLight};
  border: 2px solid
    ${(props) =>
      props.$role === "source"
        ? OS_LEGAL_COLORS.primaryBlue
        : props.$role === "target"
          ? OS_LEGAL_COLORS.green
          : OS_LEGAL_COLORS.border};
  color: ${(props) =>
    props.$role === "source"
      ? OS_LEGAL_COLORS.blueDark
      : props.$role === "target"
        ? OS_LEGAL_COLORS.successText
        : OS_LEGAL_COLORS.textSecondary};

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
`;

const AssignmentSection = styled.div`
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

export const RelationshipActionModal: React.FC<
  RelationshipActionModalProps
> = ({
  open,
  onClose,
  selectedAnnotationIds,
  existingRelationships,
  corpusId,
  documentId,
  annotations = [],
  onAddToExisting,
  onCreate,
}) => {
  const { relationLabels, selectedCorpus, setCorpus } = useCorpusState();

  // CRITICAL: Corpus is required for all relationship operations
  const hasCorpus = Boolean(corpusId && selectedCorpus?.id);

  // Helper to get annotation text preview
  const getAnnotationPreview = (annId: string): string => {
    const ann = annotations.find((a) => a.id === annId);
    if (!ann?.rawText)
      return `Annotation ${selectedAnnotationIds.indexOf(annId) + 1}`;
    const text = ann.rawText.trim();
    return text.length > 30 ? text.substring(0, 30) + "..." : text;
  };
  const [mode, setMode] = useState<"add" | "create">("add");
  const [selectedRelationshipId, setSelectedRelationshipId] = useState<
    string | null
  >(null);
  const [role, setRole] = useState<"source" | "target">("source");
  const [newLabelId, setNewLabelId] = useState<string | null>(null);
  const [sourceAnnotationIds, setSourceAnnotationIds] = useState<string[]>([]);
  const [targetAnnotationIds, setTargetAnnotationIds] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [labelSearchTerm, setLabelSearchTerm] = useState("");
  const [showCreateLabel, setShowCreateLabel] = useState(false);
  const [newLabelText, setNewLabelText] = useState("");
  const [newLabelColor, setNewLabelColor] = useState<string>(
    OS_LEGAL_COLORS.greenMedium
  );
  const [newLabelDescription, setNewLabelDescription] = useState("");

  const [smartLabelSearchOrCreate] = useMutation<
    SmartLabelSearchOrCreateOutputs,
    SmartLabelSearchOrCreateInputs
  >(SMART_LABEL_SEARCH_OR_CREATE);

  // Filter relationship labels - ONLY from current corpus's labelset
  const filteredRelationshipLabels = useMemo(() => {
    // Without a corpus, we cannot look up labels
    if (!hasCorpus || !selectedCorpus?.labelSet) {
      return [];
    }

    const labels =
      relationLabels?.filter(
        (label) => label.labelType === LabelType.RelationshipLabel
      ) || [];

    if (!labelSearchTerm) return labels;

    return labels.filter((label) =>
      label.text?.toLowerCase().includes(labelSearchTerm.toLowerCase())
    );
  }, [relationLabels, labelSearchTerm, hasCorpus, selectedCorpus?.labelSet]);

  const hasLabelset = Boolean(selectedCorpus?.labelSet);

  // Handle creating a new relationship label
  const handleCreateLabel = async () => {
    // CRITICAL: Cannot create labels without a corpus
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
          corpusId: corpusId,
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

          // Select the new label and clear search
          setNewLabelId(newLabel.id);
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
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      if (mode === "add" && selectedRelationshipId) {
        await onAddToExisting(selectedRelationshipId, role);
      } else if (mode === "create" && newLabelId) {
        await onCreate(newLabelId, sourceAnnotationIds, targetAnnotationIds);
      }
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSubmit = () => {
    if (mode === "add") {
      return (
        selectedRelationshipId !== null && selectedAnnotationIds.length > 0
      );
    } else {
      return (
        newLabelId !== null &&
        (sourceAnnotationIds.length > 0 || targetAnnotationIds.length > 0)
      );
    }
  };

  // Filter out structural relationships (user shouldn't modify these manually)
  const editableRelationships = existingRelationships.filter(
    (rel) => !rel.structural
  );

  return (
    <Modal open={open} onClose={onClose} size="sm">
      <ModalHeader
        title={
          <span>
            <Link
              size={16}
              style={{ marginRight: "0.5rem", verticalAlign: "middle" }}
            />
            Add Annotations to Relationship
          </span>
        }
        onClose={onClose}
      />
      <ModalBody>
        <ScrollableContent>
          {!hasCorpus && (
            <ErrorMessage
              title="No Corpus Selected"
              style={{ marginBottom: "1.5rem" }}
            >
              You must select a corpus to create or manage relationships.
              Relationships require a corpus context and labelset.
            </ErrorMessage>
          )}
          <div>
            <ModeSection>
              <div style={{ marginBottom: "0.75rem" }}>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    cursor: hasCorpus ? "pointer" : "default",
                  }}
                >
                  <input
                    type="radio"
                    name="relationship-mode"
                    value="add"
                    checked={mode === "add"}
                    onChange={() => setMode("add")}
                    disabled={!hasCorpus}
                  />
                  Add to existing relationship
                </label>
              </div>

              {mode === "add" && (
                <>
                  <div style={{ marginTop: "1rem", marginBottom: "0.75rem" }}>
                    <label>Select Relationship</label>
                    {editableRelationships.length === 0 ? (
                      <p
                        style={{
                          color: OS_LEGAL_COLORS.textSecondary,
                          fontStyle: "italic",
                        }}
                      >
                        No editable relationships found. Create a new one
                        instead.
                      </p>
                    ) : (
                      <div>
                        {editableRelationships.map((rel) => (
                          <RelationshipOption
                            key={rel.id}
                            $selected={selectedRelationshipId === rel.id}
                            onClick={() => setSelectedRelationshipId(rel.id)}
                          >
                            <div className="relationship-label">
                              {rel.label.icon && (
                                <DynamicIcon
                                  name={rel.label.icon as string}
                                  size={14}
                                />
                              )}
                              {rel.label.text}
                            </div>
                            <div className="relationship-stats">
                              <span>
                                <ArrowRight size={12} /> Sources:{" "}
                                {rel.sourceIds.length}
                              </span>
                              <span>
                                <Target size={12} /> Targets:{" "}
                                {rel.targetIds.length}
                              </span>
                            </div>
                          </RelationshipOption>
                        ))}
                      </div>
                    )}
                  </div>

                  {selectedRelationshipId && (
                    <div style={{ marginBottom: "0.75rem" }}>
                      <label>Add selected annotations as:</label>
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
                            cursor: "pointer",
                          }}
                        >
                          <input
                            type="radio"
                            name="annotation-role"
                            value="source"
                            checked={role === "source"}
                            onChange={() => setRole("source")}
                          />
                          Source annotations
                        </label>
                        <label
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                            cursor: "pointer",
                          }}
                        >
                          <input
                            type="radio"
                            name="annotation-role"
                            value="target"
                            checked={role === "target"}
                            onChange={() => setRole("target")}
                          />
                          Target annotations
                        </label>
                      </div>
                    </div>
                  )}
                </>
              )}
            </ModeSection>

            <ModeSection>
              <div style={{ marginBottom: "0.75rem" }}>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    cursor: hasCorpus ? "pointer" : "default",
                  }}
                >
                  <input
                    type="radio"
                    name="relationship-mode"
                    value="create"
                    checked={mode === "create"}
                    onChange={() => setMode("create")}
                    disabled={!hasCorpus}
                  />
                  Create new relationship
                </label>
              </div>

              {mode === "create" && (
                <>
                  {!newLabelId ? (
                    <>
                      {!hasLabelset && (
                        <WarningMessage style={{ marginTop: "1rem" }}>
                          <strong>No labelset found.</strong> Creating a label
                          will automatically create a labelset for this corpus.
                        </WarningMessage>
                      )}

                      {!showCreateLabel ? (
                        <>
                          <div
                            style={{
                              marginTop: "1rem",
                              marginBottom: "0.75rem",
                            }}
                          >
                            <label>Search or Create Relationship Label</label>
                            <Input
                              fullWidth
                              placeholder="Search for a relationship label..."
                              value={labelSearchTerm}
                              onChange={(
                                e: React.ChangeEvent<HTMLInputElement>
                              ) => setLabelSearchTerm(e.target.value)}
                            />
                          </div>

                          {filteredRelationshipLabels.length > 0 ? (
                            <div style={{ marginBottom: "0.75rem" }}>
                              <label>Select from existing labels:</label>
                              <Dropdown
                                placeholder="Select relationship label"
                                fluid
                                mode="select"
                                searchable="local"
                                options={filteredRelationshipLabels.map(
                                  (label) => ({
                                    value: label.id,
                                    label: label.text || "",
                                    icon: label.icon || undefined,
                                  })
                                )}
                                value={newLabelId ?? null}
                                onChange={(value) =>
                                  setNewLabelId(value as string)
                                }
                              />
                            </div>
                          ) : (
                            <p
                              style={{
                                color: OS_LEGAL_COLORS.textSecondary,
                                fontStyle: "italic",
                                margin: "0.5rem 0",
                              }}
                            >
                              No matching labels found.
                            </p>
                          )}

                          {labelSearchTerm && (
                            <Button
                              variant="primary"
                              leftIcon={<Plus size={14} />}
                              onClick={() => {
                                setNewLabelText(labelSearchTerm);
                                setShowCreateLabel(true);
                              }}
                              style={{ marginTop: "0.5rem" }}
                            >
                              Create &quot;{labelSearchTerm}&quot; label
                            </Button>
                          )}
                        </>
                      ) : (
                        <>
                          <div
                            style={{
                              marginTop: "1rem",
                              marginBottom: "0.75rem",
                            }}
                          >
                            <label>Label Name</label>
                            <Input
                              fullWidth
                              placeholder="Enter label name"
                              value={newLabelText}
                              onChange={(
                                e: React.ChangeEvent<HTMLInputElement>
                              ) => setNewLabelText(e.target.value)}
                            />
                          </div>

                          <div style={{ marginBottom: "0.75rem" }}>
                            <label>Color</label>
                            <input
                              type="color"
                              value={newLabelColor}
                              onChange={(e) => setNewLabelColor(e.target.value)}
                            />
                          </div>

                          <div style={{ marginBottom: "0.75rem" }}>
                            <label>Description (optional)</label>
                            <Input
                              fullWidth
                              placeholder="Enter description"
                              value={newLabelDescription}
                              onChange={(
                                e: React.ChangeEvent<HTMLInputElement>
                              ) => setNewLabelDescription(e.target.value)}
                            />
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
                            >
                              Cancel
                            </Button>
                            <Button
                              variant="primary"
                              onClick={handleCreateLabel}
                            >
                              Create Label
                            </Button>
                          </div>
                        </>
                      )}
                    </>
                  ) : (
                    <>
                      <div
                        style={{ marginTop: "1rem", marginBottom: "0.75rem" }}
                      >
                        <label>Selected Label</label>
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
                          <span style={{ fontWeight: 500 }}>
                            {
                              relationLabels?.find((l) => l.id === newLabelId)
                                ?.text
                            }
                          </span>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setNewLabelId(null);
                              setLabelSearchTerm("");
                            }}
                          >
                            Change
                          </Button>
                        </div>
                      </div>

                      <AssignmentSection>
                        <div className="section-title">
                          <ArrowRight
                            size={14}
                            color={OS_LEGAL_COLORS.primaryBlue}
                          />
                          Source Annotations
                        </div>
                        <div className="pills-container">
                          {selectedAnnotationIds.map((annId) => {
                            const isSource =
                              sourceAnnotationIds.includes(annId);
                            const isTarget =
                              targetAnnotationIds.includes(annId);
                            const role = isSource
                              ? "source"
                              : isTarget
                                ? "target"
                                : "unassigned";
                            return (
                              <AnnotationPill
                                key={annId}
                                $role={role}
                                onClick={() => {
                                  if (isSource) {
                                    setSourceAnnotationIds((prev) =>
                                      prev.filter((id) => id !== annId)
                                    );
                                  } else {
                                    setSourceAnnotationIds((prev) => [
                                      ...prev,
                                      annId,
                                    ]);
                                    setTargetAnnotationIds((prev) =>
                                      prev.filter((id) => id !== annId)
                                    );
                                  }
                                }}
                              >
                                {role === "source" && <Check size={12} />}
                                {getAnnotationPreview(annId)}
                              </AnnotationPill>
                            );
                          })}
                        </div>
                      </AssignmentSection>

                      <AssignmentSection>
                        <div className="section-title">
                          <Target size={14} color={OS_LEGAL_COLORS.green} />
                          Target Annotations
                        </div>
                        <div className="pills-container">
                          {selectedAnnotationIds.map((annId) => {
                            const isSource =
                              sourceAnnotationIds.includes(annId);
                            const isTarget =
                              targetAnnotationIds.includes(annId);
                            const role = isSource
                              ? "source"
                              : isTarget
                                ? "target"
                                : "unassigned";
                            return (
                              <AnnotationPill
                                key={annId}
                                $role={role}
                                onClick={() => {
                                  if (isTarget) {
                                    setTargetAnnotationIds((prev) =>
                                      prev.filter((id) => id !== annId)
                                    );
                                  } else {
                                    setTargetAnnotationIds((prev) => [
                                      ...prev,
                                      annId,
                                    ]);
                                    setSourceAnnotationIds((prev) =>
                                      prev.filter((id) => id !== annId)
                                    );
                                  }
                                }}
                              >
                                {role === "target" && <Check size={12} />}
                                {getAnnotationPreview(annId)}
                              </AnnotationPill>
                            );
                          })}
                        </div>
                      </AssignmentSection>

                      <p
                        style={{
                          fontSize: "0.875rem",
                          color: OS_LEGAL_COLORS.textSecondary,
                          marginTop: "1rem",
                          fontStyle: "italic",
                        }}
                      >
                        Click an annotation to assign it as source or target.
                        You can leave some unassigned and add them later.
                      </p>
                    </>
                  )}
                </>
              )}
            </ModeSection>
          </div>

          <InfoBox>
            <strong>
              <Info
                size={14}
                style={{
                  display: "inline",
                  verticalAlign: "middle",
                  marginRight: "0.5rem",
                }}
              />
              Selected: {selectedAnnotationIds.length} annotation
              {selectedAnnotationIds.length !== 1 ? "s" : ""}
            </strong>
          </InfoBox>
        </ScrollableContent>
      </ModalBody>

      <ModalFooter>
        <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={!hasCorpus || !canSubmit() || isSubmitting}
        >
          {isSubmitting
            ? "Submitting..."
            : mode === "add"
              ? "Add to Relationship"
              : "Create Relationship"}
        </Button>
      </ModalFooter>
    </Modal>
  );
};
