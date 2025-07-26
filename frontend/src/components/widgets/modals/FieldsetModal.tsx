import React, { useState, useEffect, useMemo } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
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
import {
  X,
  Database,
  Plus,
  GripVertical,
  ChevronDown,
  ChevronUp,
  Edit3,
  Trash2,
  AlertCircle,
  Save,
  Loader2,
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

// Styled Components
const ModalOverlay = styled(motion.div)`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999999;
  padding: 1rem;
`;

const ModalContainer = styled(motion.div)`
  background: white;
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  max-width: 800px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const ModalHeader = styled.div`
  padding: 2rem 2rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #fafbfc 0%, rgba(250, 251, 252, 0) 100%);
`;

const HeaderTitle = styled.h2`
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

const HeaderSubtitle = styled.p`
  margin: 0.5rem 0 0;
  color: #64748b;
  font-size: 0.9375rem;
  line-height: 1.5;
`;

const CloseButton = styled(motion.button)`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    width: 20px;
    height: 20px;
    color: #64748b;
  }

  &:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
    svg {
      color: #475569;
    }
  }
`;

const ModalContent = styled.div`
  padding: 2rem;
  flex: 1;
  overflow-y: auto;
`;

const FormSection = styled.div`
  margin-bottom: 2rem;
`;

const Label = styled.label`
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.5rem;
`;

const Input = styled.input`
  width: 100%;
  padding: 0.875rem 1rem;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 0.9375rem;
  transition: all 0.2s ease;
  background: white;

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &:disabled {
    background: #f8fafc;
    cursor: not-allowed;
  }
`;

const TextArea = styled.textarea`
  width: 100%;
  padding: 0.875rem 1rem;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 0.9375rem;
  font-family: inherit;
  resize: vertical;
  min-height: 100px;
  transition: all 0.2s ease;
  background: white;

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &:disabled {
    background: #f8fafc;
    cursor: not-allowed;
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
  color: #0f172a;
  margin: 0;
`;

const AddColumnButton = styled(motion.button).attrs({
  type: "button",
})`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: #2563eb;
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
  border: 2px dashed #e2e8f0;
  border-radius: 12px;
  background: #fafbfc;
`;

const EmptyStateText = styled.p`
  color: #64748b;
  font-size: 0.9375rem;
  margin: 0 0 1rem;
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2rem;
  border-top: 1px solid #e2e8f0;
  background: #fafbfc;
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const ValidationMessage = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #dc2626;
  font-size: 0.875rem;

  svg {
    width: 16px;
    height: 16px;
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 0.75rem;
`;

const Button = styled(motion.button)<{ $variant?: "primary" | "secondary" }>`
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;

  ${(props) =>
    props.$variant === "primary"
      ? `
    background: #3b82f6;
    color: white;
    border: 2px solid #3b82f6;

    &:hover:not(:disabled) {
      background: #2563eb;
      border-color: #2563eb;
    }

    &:disabled {
      background: #94a3b8;
      border-color: #94a3b8;
      cursor: not-allowed;
    }
  `
      : `
    background: white;
    color: #64748b;
    border: 2px solid #e2e8f0;

    &:hover:not(:disabled) {
      background: #f8fafc;
      border-color: #cbd5e1;
      color: #475569;
    }
  `}
`;

const SpinningLoader = styled(motion.div)`
  color: #3b82f6;
`;

// Collapsible Column Card Component
const ColumnCard = styled(motion.div)<{ $isDragging?: boolean }>`
  background: white;
  border: 2px solid ${(props) => (props.$isDragging ? "#3b82f6" : "#e2e8f0")};
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.2s ease;
  box-shadow: ${(props) =>
    props.$isDragging
      ? "0 10px 30px -10px rgba(59, 130, 246, 0.3)"
      : "0 1px 3px 0 rgba(0, 0, 0, 0.1)"};
`;

const ColumnHeader = styled.div`
  padding: 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  user-select: none;

  &:hover {
    background: #f8fafc;
  }
`;

const DragHandle = styled.div`
  color: #94a3b8;
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
  color: #0f172a;
`;

const ColumnType = styled.span`
  font-size: 0.75rem;
  color: #64748b;
  background: #f1f5f9;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  margin-top: 0.25rem;
  display: inline-block;
`;

const ColumnActions = styled.div`
  display: flex;
  gap: 0.5rem;
`;

const IconButton = styled(motion.button)`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    width: 16px;
    height: 16px;
    color: #64748b;
  }

  &:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
    svg {
      color: #475569;
    }
  }
`;

const ExpandIcon = styled.div<{ $expanded: boolean }>`
  transition: transform 0.2s ease;
  transform: rotate(${(props) => (props.$expanded ? "180deg" : "0")});
  color: #64748b;

  svg {
    width: 20px;
    height: 20px;
  }
`;

const ColumnDetails = styled(motion.div)`
  padding: 0 1rem 1rem;
  border-top: 1px solid #e2e8f0;
`;

const DetailRow = styled.div`
  margin-top: 0.75rem;
`;

const DetailLabel = styled.span`
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

const DetailValue = styled.p`
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: #1e293b;
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
          <IconButton
            onClick={() => onEdit(column)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <Edit3 />
          </IconButton>
          <IconButton
            onClick={() => onDelete(column.id)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <Trash2 />
          </IconButton>
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
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [columns, setColumns] = useState<ColumnTypeFromAPI[]>([]);
  const [editingColumn, setEditingColumn] = useState<ColumnTypeFromAPI | null>(
    null
  );
  const [isColumnModalOpen, setIsColumnModalOpen] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  const isEditMode = mode === "edit" && existingFieldset;

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

  if (!open) return null;

  return (
    <>
      <ModalOverlay
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <ModalContainer
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
        >
          <ModalHeader>
            <HeaderTitle>
              <Database size={24} />
              {isEditMode ? "Edit Fieldset" : "Create New Fieldset"}
            </HeaderTitle>
            <HeaderSubtitle>
              Define the structure for extracting data from documents
            </HeaderSubtitle>
            <CloseButton
              onClick={onClose}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <X />
            </CloseButton>
          </ModalHeader>

          <ModalContent>
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
          </ModalContent>

          <ModalFooter>
            {!canSave && (
              <ValidationMessage>
                <AlertCircle />
                {!name.trim()
                  ? "Please provide a fieldset name"
                  : "Please add at least one column"}
              </ValidationMessage>
            )}
            {canSave && <div />}
            <ButtonGroup>
              <Button
                onClick={onClose}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Cancel
              </Button>
              <Button
                $variant="primary"
                onClick={handleSave}
                disabled={!canSave || isLoading}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {isLoading ? (
                  <>
                    <SpinningLoader
                      animate={{ rotate: 360 }}
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        ease: "linear",
                      }}
                    >
                      <Loader2 size={18} />
                    </SpinningLoader>
                    Saving...
                  </>
                ) : (
                  <>
                    <Save size={18} />
                    {isEditMode ? "Update Fieldset" : "Create Fieldset"}
                  </>
                )}
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
    </>
  );
};
