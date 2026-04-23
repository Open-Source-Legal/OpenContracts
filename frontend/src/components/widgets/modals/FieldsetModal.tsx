import React, { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { motion, AnimatePresence } from "framer-motion";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Button } from "@os-legal/ui";
import {
  X,
  Database,
  Plus,
  GripVertical,
  ChevronDown,
  Edit3,
  Trash2,
  AlertCircle,
  Save,
} from "lucide-react";
import {
  REQUEST_CREATE_FIELDSET,
  REQUEST_UPDATE_FIELDSET,
  REQUEST_CREATE_COLUMN,
  REQUEST_UPDATE_COLUMN,
  REQUEST_DELETE_COLUMN,
  RequestCreateFieldsetInputType,
  RequestCreateFieldsetOutputType,
  RequestUpdateFieldsetInputType,
  RequestUpdateFieldsetOutputType,
  RequestCreateColumnInputType,
  RequestCreateColumnOutputType,
  RequestUpdateColumnInputType,
  RequestUpdateColumnOutputType,
  RequestDeleteColumnInputType,
  RequestDeleteColumnOutputType,
} from "../../../graphql/mutations";
import {
  GET_FIELDSETS,
  REQUEST_GET_FIELDSET,
  GetFieldsetInput,
  GetFieldsetOutput,
} from "../../../graphql/queries";
import {
  FieldsetType,
  ColumnType as ColumnTypeFromAPI,
} from "../../../types/graphql-api";
import { CreateColumnModal } from "./CreateColumnModal";

// Styled Components — aligned with CreateExtractModal gold standard
const ModalOverlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
`;

const ModalContainer = styled(motion.div)`
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
    0 10px 10px -5px rgba(0, 0, 0, 0.04);
  max-width: 800px;
  width: 100%;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  @media (max-width: 768px) {
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
  }
`;

const ModalHeader = styled.div`
  padding: 2rem 2.5rem 1.75rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  position: relative;
  background: linear-gradient(
    to bottom,
    #fbfcfd 0%,
    ${OS_LEGAL_COLORS.gray50} 100%
  );
`;

const ModalTitle = styled.h2`
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  letter-spacing: -0.025em;
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

const ModalSubtitle = styled.p`
  margin: 0.625rem 0 0;
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.5;
  max-width: 85%;
`;

const CloseButton = styled(motion.button)`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: none;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

  svg {
    width: 20px;
    height: 20px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);

    svg {
      color: ${OS_LEGAL_COLORS.textTertiary};
    }
  }
`;

const ModalBody = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 2rem 2.5rem;
  background: white;

  @media (max-width: 768px) {
    padding: 1.5rem;
  }
`;

const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  margin-bottom: 1.75rem;
`;

const Label = styled.label`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: flex;
  align-items: center;
  gap: 0.25rem;
  letter-spacing: 0.025em;
`;

const Input = styled.input`
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  font-size: 0.9375rem;
  transition: all 0.2s ease;
  background: #ffffff;
  color: ${OS_LEGAL_COLORS.textPrimary};
  box-sizing: border-box;

  &:hover:not(:focus) {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
    background: #ffffff;
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }

  &:disabled {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    cursor: not-allowed;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const TextArea = styled.textarea`
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  font-size: 0.9375rem;
  font-family: inherit;
  resize: vertical;
  min-height: 100px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: ${OS_LEGAL_COLORS.textPrimary};
  box-sizing: border-box;

  &:hover:not(:focus) {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
    background: #ffffff;
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }

  &:disabled {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    cursor: not-allowed;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const ColumnsSection = styled.div`
  margin-top: 2rem;
`;

const SectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
`;

const SectionTitle = styled.h3`
  font-size: 1.125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
`;

const AddColumnButton = styled(motion.button).attrs({
  type: "button",
})`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.primaryBlueHover};
  }
`;

const ColumnsList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 3rem 1rem;
  border: 1.5px dashed ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

const EmptyStateText = styled.p`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.9375rem;
  margin: 0 0 1rem;
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2.5rem 1.75rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: linear-gradient(
    to top,
    #fbfcfd 0%,
    ${OS_LEGAL_COLORS.gray50} 100%
  );
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;

  @media (max-width: 640px) {
    flex-direction: column-reverse;
    padding: 1.25rem 1.5rem;
  }
`;

const FooterInfo = styled.div`
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  gap: 0.5rem;

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: 640px) {
    text-align: center;
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 0.75rem;

  @media (max-width: 640px) {
    width: 100%;
    flex-direction: column-reverse;
  }
`;

// Collapsible Column Card Component
const ColumnCard = styled(motion.div)<{ $isDragging?: boolean }>`
  background: white;
  border: 1.5px solid
    ${(props) =>
      props.$isDragging ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 10px;
  overflow: hidden;
  transition: all 0.2s ease;
  box-shadow: ${(props) =>
    props.$isDragging
      ? "0 10px 30px -10px rgba(59, 130, 246, 0.3)"
      : "0 1px 3px 0 rgba(0, 0, 0, 0.06)"};
`;

const ColumnHeader = styled.div`
  padding: 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  user-select: none;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

const DragHandle = styled.div`
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: grab;

  &:active {
    cursor: grabbing;
  }

  svg {
    width: 20px;
    height: 20px;
  }
`;

const ColumnInfo = styled.div`
  flex: 1;
`;

const ColumnName = styled.h4`
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const ColumnType = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  margin-top: 0.25rem;
  display: inline-block;
`;

const ColumnActions = styled.div`
  display: flex;
  gap: 0.5rem;
`;

const IconBtn = styled(motion.button)`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    svg {
      color: ${OS_LEGAL_COLORS.textTertiary};
    }
  }
`;

const ExpandIcon = styled.div<{ $expanded: boolean }>`
  transition: transform 0.2s ease;
  transform: rotate(${(props) => (props.$expanded ? "180deg" : "0")});
  color: ${OS_LEGAL_COLORS.textSecondary};

  svg {
    width: 20px;
    height: 20px;
  }
`;

const ColumnDetails = styled(motion.div)`
  padding: 0 1rem 1rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
`;

const DetailRow = styled.div`
  margin-top: 0.75rem;
`;

const DetailLabel = styled.span`
  font-size: 0.75rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

const DetailValue = styled.p`
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: pre-wrap;
`;

// Component
interface FieldsetModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (fieldset: FieldsetType) => void;
  existingFieldset?: FieldsetType | null;
  mode?: "create" | "edit";
}

interface CollapsibleColumnCardProps {
  column: ColumnTypeFromAPI;
  index: number;
  onEdit: (column: ColumnTypeFromAPI) => void;
  onDelete: (columnId: string) => void;
}

const CollapsibleColumnCard: React.FC<CollapsibleColumnCardProps> = ({
  column,
  index,
  onEdit,
  onDelete,
}) => {
  const [expanded, setExpanded] = useState(false);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: column.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <ColumnCard
      ref={setNodeRef}
      style={style}
      $isDragging={isDragging}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
    >
      <ColumnHeader onClick={() => setExpanded(!expanded)}>
        <div {...attributes} {...listeners}>
          <DragHandle>
            <GripVertical />
          </DragHandle>
        </div>
        <ColumnInfo>
          <ColumnName>{column.name}</ColumnName>
          <ColumnType>{column.outputType}</ColumnType>
        </ColumnInfo>
        <ColumnActions onClick={(e) => e.stopPropagation()}>
          <IconBtn
            onClick={() => onEdit(column)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <Edit3 />
          </IconBtn>
          <IconBtn
            onClick={() => onDelete(column.id)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            aria-label="Delete column"
          >
            <Trash2 />
          </IconBtn>
        </ColumnActions>
        <ExpandIcon $expanded={expanded}>
          <ChevronDown />
        </ExpandIcon>
      </ColumnHeader>
      <AnimatePresence>
        {expanded && (
          <ColumnDetails
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {column.query && (
              <DetailRow>
                <DetailLabel>Query</DetailLabel>
                <DetailValue>{column.query}</DetailValue>
              </DetailRow>
            )}
            {column.matchText && (
              <DetailRow>
                <DetailLabel>Match Text</DetailLabel>
                <DetailValue>{column.matchText}</DetailValue>
              </DetailRow>
            )}
            {column.instructions && (
              <DetailRow>
                <DetailLabel>Instructions</DetailLabel>
                <DetailValue>{column.instructions}</DetailValue>
              </DetailRow>
            )}
            {column.limitToLabel && (
              <DetailRow>
                <DetailLabel>Limit to Label</DetailLabel>
                <DetailValue>{column.limitToLabel}</DetailValue>
              </DetailRow>
            )}
            {column.extractIsList && (
              <DetailRow>
                <DetailLabel>Extract as List</DetailLabel>
                <DetailValue>Yes</DetailValue>
              </DetailRow>
            )}
          </ColumnDetails>
        )}
      </AnimatePresence>
    </ColumnCard>
  );
};

export const FieldsetModal: React.FC<FieldsetModalProps> = ({
  open,
  onClose,
  onSuccess,
  existingFieldset,
  mode = "create",
}) => {
  const [isMounted, setIsMounted] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [columns, setColumns] = useState<ColumnTypeFromAPI[]>([]);
  const [editingColumn, setEditingColumn] = useState<ColumnTypeFromAPI | null>(
    null
  );
  const [isColumnModalOpen, setIsColumnModalOpen] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  const isEditMode = mode === "edit" && existingFieldset;

  // Delay mount slightly so any phantom click from the trigger button
  // (e.g. dropdown option removed mid-click) is absorbed before the
  // overlay becomes interactive.
  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => setIsMounted(true), 50);
      return () => clearTimeout(timer);
    } else {
      setIsMounted(false);
    }
  }, [open]);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Fetch fieldset details if editing
  const { loading: loadingFieldset, refetch } = useQuery<
    GetFieldsetOutput,
    GetFieldsetInput
  >(REQUEST_GET_FIELDSET, {
    variables: { id: existingFieldset?.id || "" },
    skip: !isEditMode,
    onCompleted: (data) => {
      if (data?.fieldset) {
        setName(data.fieldset.name);
        setDescription(data.fieldset.description);
        setColumns(data.fieldset.fullColumnList || []);
      }
    },
  });

  // Mutations
  const [createFieldset, { loading: creatingFieldset }] = useMutation<
    RequestCreateFieldsetOutputType,
    RequestCreateFieldsetInputType
  >(REQUEST_CREATE_FIELDSET);

  const [updateFieldset, { loading: updatingFieldset }] = useMutation<
    RequestUpdateFieldsetOutputType,
    RequestUpdateFieldsetInputType
  >(REQUEST_UPDATE_FIELDSET);

  const [createColumn, { loading: creatingColumn }] = useMutation<
    RequestCreateColumnOutputType,
    RequestCreateColumnInputType
  >(REQUEST_CREATE_COLUMN);

  const [updateColumn, { loading: updatingColumn }] = useMutation<
    RequestUpdateColumnOutputType,
    RequestUpdateColumnInputType
  >(REQUEST_UPDATE_COLUMN);

  const [deleteColumn, { loading: deletingColumn }] = useMutation<
    RequestDeleteColumnOutputType,
    RequestDeleteColumnInputType
  >(REQUEST_DELETE_COLUMN);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setColumns([]);
      setEditingColumn(null);
      setIsDirty(false);
    }
  }, [open]);

  // Handle drag and drop
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (active.id === over?.id) {
      return;
    }

    const oldIndex = columns.findIndex((column) => column.id === active.id);
    const newIndex = columns.findIndex((column) => column.id === over?.id);

    if (oldIndex === -1 || newIndex === -1) {
      return;
    }

    setColumns(arrayMove(columns, oldIndex, newIndex));
    setIsDirty(true);
  };

  // Handle column operations
  const handleAddColumn = () => {
    // Explicitly ensure editingColumn is null for new columns
    setEditingColumn(null);
    setIsColumnModalOpen(true);
  };

  const handleEditColumn = (column: ColumnTypeFromAPI) => {
    setEditingColumn(column);
    setIsColumnModalOpen(true);
  };

  const handleDeleteColumn = async (columnId: string) => {
    if (isEditMode && existingFieldset?.inUse) {
      toast.error(
        "Cannot delete columns from a fieldset that is in use. Create a copy first."
      );
      return;
    }

    try {
      if (isEditMode) {
        await deleteColumn({ variables: { id: columnId } });
        toast.success("Column deleted successfully");
      }
      setColumns(columns.filter((col) => col.id !== columnId));
      setIsDirty(true);
    } catch (error) {
      toast.error("Failed to delete column");
    }
  };

  const handleColumnSubmit = async (data: any) => {
    try {
      if (editingColumn) {
        if (isEditMode) {
          const result = await updateColumn({
            variables: {
              id: editingColumn.id,
              ...data,
            },
          });
          if (result.data?.updateColumn.ok) {
            setColumns(
              columns.map((col) =>
                col.id === editingColumn.id ? { ...col, ...data } : col
              )
            );
            toast.success("Column updated successfully");
          }
        } else {
          // Just update local state for new fieldsets
          setColumns(
            columns.map((col) =>
              col.id === editingColumn.id ? { ...col, ...data } : col
            )
          );
        }
      } else {
        // Adding new column
        const tempId = `temp-${Date.now()}`;
        const newColumn: ColumnTypeFromAPI = {
          id: tempId,
          ...data,
        };
        setColumns([...columns, newColumn]);
        setIsDirty(true);
        toast.success("Column added successfully");
      }
      setIsColumnModalOpen(false);
      setEditingColumn(null);
    } catch (error) {
      toast.error("Failed to update column");
    }
  };

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Please provide a fieldset name");
      return;
    }

    if (columns.length === 0) {
      toast.error("Please add at least one column");
      return;
    }

    try {
      let fieldsetId: string;

      if (isEditMode && existingFieldset) {
        // Check if fieldset is in use
        if (existingFieldset.inUse) {
          // Create a copy
          const { data } = await createFieldset({
            variables: {
              name: `${name} (copy)`,
              description,
            },
          });
          fieldsetId = data?.createFieldset.obj.id || "";
          toast.info("Created a copy of the in-use fieldset");
        } else {
          // Update existing
          const { data } = await updateFieldset({
            variables: {
              id: existingFieldset.id,
              name,
              description,
            },
          });
          fieldsetId = existingFieldset.id;
        }
      } else {
        // Create new fieldset
        const { data } = await createFieldset({
          variables: {
            name,
            description,
          },
        });
        fieldsetId = data?.createFieldset.obj.id || "";
      }

      // Create columns for new fieldset
      if (fieldsetId) {
        await Promise.all(
          columns.map((column) =>
            createColumn({
              variables: {
                fieldsetId,
                name: column.name,
                query: column.query || "",
                matchText: column.matchText,
                outputType: column.outputType,
                limitToLabel: column.limitToLabel,
                instructions: column.instructions,
                taskName: column.taskName,
              },
            })
          )
        );

        toast.success(
          isEditMode
            ? "Fieldset updated successfully"
            : "Fieldset created successfully"
        );

        if (onSuccess) {
          onSuccess({ id: fieldsetId, name, description } as FieldsetType);
        }
        onClose();
      }
    } catch (error) {
      toast.error("Failed to save fieldset");
    }
  };

  const isLoading =
    loadingFieldset ||
    creatingFieldset ||
    updatingFieldset ||
    creatingColumn ||
    updatingColumn ||
    deletingColumn;

  const canSave = name.trim() && columns.length > 0;

  if (!open || !isMounted) return null;

  return createPortal(
    <>
      <ModalOverlay onClick={onClose}>
        <ModalContainer
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
        >
          <ModalHeader>
            <ModalTitle>
              <Database size={24} />
              {isEditMode ? "Edit Fieldset" : "Create New Fieldset"}
            </ModalTitle>
            <ModalSubtitle>
              Define the structure for extracting data from documents
            </ModalSubtitle>
            <CloseButton
              onClick={onClose}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              aria-label="Close"
            >
              <X />
            </CloseButton>
          </ModalHeader>

          <ModalBody>
            <FormSection>
              <Label>Name</Label>
              <Input
                type="text"
                placeholder="Enter fieldset name..."
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setIsDirty(true);
                }}
                disabled={isLoading}
              />
            </FormSection>

            <FormSection>
              <Label>Description</Label>
              <TextArea
                placeholder="Describe what this fieldset extracts..."
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                  setIsDirty(true);
                }}
                disabled={isLoading}
              />
            </FormSection>

            <ColumnsSection>
              <SectionHeader>
                <SectionTitle>Columns ({columns.length})</SectionTitle>
                <AddColumnButton
                  onClick={(e: React.MouseEvent) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleAddColumn();
                  }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Plus size={16} />
                  Add Column
                </AddColumnButton>
              </SectionHeader>

              {columns.length === 0 ? (
                <EmptyState>
                  <EmptyStateText>
                    No columns yet. Add columns to define what data to extract.
                  </EmptyStateText>
                  <AddColumnButton
                    onClick={(e: React.MouseEvent) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleAddColumn();
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                  >
                    <Plus size={16} />
                    Add First Column
                  </AddColumnButton>
                </EmptyState>
              ) : (
                <DndContext
                  sensors={sensors}
                  collisionDetection={closestCenter}
                  onDragEnd={handleDragEnd}
                >
                  <SortableContext
                    items={columns.map((column) => column.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    <ColumnsList>
                      <AnimatePresence>
                        {columns.map((column, index) => (
                          <CollapsibleColumnCard
                            key={column.id}
                            column={column}
                            index={index}
                            onEdit={handleEditColumn}
                            onDelete={handleDeleteColumn}
                          />
                        ))}
                      </AnimatePresence>
                    </ColumnsList>
                  </SortableContext>
                </DndContext>
              )}
            </ColumnsSection>
          </ModalBody>

          <ModalFooter>
            <FooterInfo>
              {!canSave ? (
                <>
                  <AlertCircle />
                  {!name.trim()
                    ? "Please provide a fieldset name"
                    : "Please add at least one column"}
                </>
              ) : isEditMode ? (
                "Editing existing fieldset definition"
              ) : (
                "All required fields must be filled before submitting"
              )}
            </FooterInfo>
            <ButtonGroup>
              <Button
                variant="secondary"
                onClick={onClose}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSave}
                loading={isLoading}
                disabled={!canSave || isLoading}
                leftIcon={<Save size={16} />}
              >
                {isEditMode ? "Update Fieldset" : "Create Fieldset"}
              </Button>
            </ButtonGroup>
          </ModalFooter>
        </ModalContainer>
      </ModalOverlay>

      <CreateColumnModal
        open={isColumnModalOpen}
        existing_column={editingColumn}
        onClose={() => {
          setIsColumnModalOpen(false);
          setEditingColumn(null);
        }}
        onSubmit={handleColumnSubmit}
      />
    </>,
    document.body
  );
};
