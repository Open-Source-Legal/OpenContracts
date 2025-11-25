import React, { useState, useEffect } from "react";
import {
  Table,
  Button,
  Icon,
  Popup,
  Confirm,
  Loader,
  Message,
  Dropdown,
} from "semantic-ui-react";
import { useQuery, useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
// import { DragDropContext, Droppable, Draggable } from "react-beautiful-dnd";

import {
  GET_CORPUS_METADATA_COLUMNS,
  CREATE_METADATA_COLUMN,
  UPDATE_METADATA_COLUMN,
  DELETE_METADATA_COLUMN,
  GetCorpusMetadataColumnsInput,
  GetCorpusMetadataColumnsOutput,
  CreateMetadataColumnInput,
  CreateMetadataColumnOutput,
  UpdateMetadataColumnInput,
  UpdateMetadataColumnOutput,
  DeleteMetadataColumnInput,
  DeleteMetadataColumnOutput,
} from "../../graphql/metadataOperations";
import { MetadataColumn } from "../../types/metadata";
import { MetadataColumnModal } from "../widgets/modals/MetadataColumnModal";

interface CorpusMetadataSettingsProps {
  corpusId: string;
}

const Container = styled.div`
  padding: 0;
  height: 100%;
  background: transparent;
`;

const HeaderSection = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
  }

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 1rem;
  }
`;

const Title = styled.h3`
  margin: 0 0 0.5rem 0;
  color: #0f172a;
  font-size: 1.375rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #1e293b 0%, #475569 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
`;

const HelperText = styled.p`
  color: #64748b;
  font-size: 0.9375rem;
  margin: 0;
  line-height: 1.6;
  max-width: 600px;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 4rem 2rem;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 16px;
  border: 2px dashed #e2e8f0;
  color: #64748b;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    border-color: #cbd5e1;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  }

  .icon {
    font-size: 4rem;
    margin-bottom: 1.5rem;
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    opacity: 0.5;
  }

  h4 {
    color: #1e293b;
    font-size: 1.25rem;
    font-weight: 700;
    margin-bottom: 0.75rem;
    letter-spacing: -0.02em;
  }

  p {
    margin-bottom: 2rem;
    font-size: 0.9375rem;
    line-height: 1.6;
    color: #64748b;
  }
`;

const StyledTable = styled(Table)`
  &.ui.table {
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.08);
    border: 1px solid #e2e8f0;
    background: white;

    thead th {
      background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
      font-weight: 700;
      color: #475569;
      text-transform: uppercase;
      font-size: 0.8125rem;
      letter-spacing: 0.08em;
      padding: 1rem 1.25rem;
      border-bottom: 2px solid #e2e8f0;
    }

    tbody tr {
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      border-bottom: 1px solid #f1f5f9;

      &:last-child {
        border-bottom: none;
      }

      &:hover {
        background: linear-gradient(135deg, #fafbfc 0%, #f8fafc 100%);
        transform: translateX(2px);
        box-shadow: inset 3px 0 0 #6366f1;
      }

      td {
        padding: 1rem 1.25rem;
        color: #1e293b;
        font-size: 0.9375rem;
      }
    }
  }
`;

const OrderButtons = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.375rem;

  button {
    transition: all 0.2s ease !important;
    border-radius: 8px !important;
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%) !important;
    border: 1px solid #e2e8f0 !important;

    &:not(:disabled):hover {
      background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
      border-color: transparent !important;
      color: white !important;
      transform: scale(1.05);
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
    }

    &:disabled {
      opacity: 0.3 !important;
    }
  }
`;

const DataTypeBadge = styled.span<{ dataType: string }>`
  display: inline-flex;
  align-items: center;
  padding: 0.375rem 0.875rem;
  border-radius: 100px;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.025em;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;

  background: ${(props) => {
    switch (props.dataType) {
      case "STRING":
      case "TEXT":
        return "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)";
      case "INTEGER":
      case "FLOAT":
        return "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)";
      case "BOOLEAN":
        return "linear-gradient(135deg, #10b981 0%, #059669 100%)";
      case "DATE":
      case "DATETIME":
        return "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)";
      case "CHOICE":
      case "MULTI_CHOICE":
        return "linear-gradient(135deg, #ec4899 0%, #db2777 100%)";
      case "JSON":
        return "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)";
      default:
        return "linear-gradient(135deg, #64748b 0%, #475569 100%)";
    }
  }};
  color: white;

  &::before {
    content: "";
    position: absolute;
    top: 50%;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.2),
      transparent
    );
    transform: translateY(-50%);
    transition: left 0.5s ease;
  }

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

    &::before {
      left: 100%;
    }
  }
`;

const RequiredBadge = styled.span`
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.625rem;
  border-radius: 100px;
  font-size: 0.75rem;
  font-weight: 700;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  color: #dc2626;
  border: 1px solid #fecaca;
  margin-left: 0.625rem;
  letter-spacing: 0.025em;
  text-transform: uppercase;
  box-shadow: 0 2px 6px rgba(220, 38, 38, 0.1);
  transition: all 0.2s ease;

  &:hover {
    transform: scale(1.05);
    box-shadow: 0 3px 8px rgba(220, 38, 38, 0.15);
  }
`;

const AddFieldButton = styled(Button)`
  &&& {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    color: white;
    border: none;
    padding: 0.875rem 1.5rem;
    font-weight: 600;
    border-radius: 12px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 14px rgba(99, 102, 241, 0.25);
    position: relative;
    overflow: hidden;

    &::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: linear-gradient(135deg, #818cf8 0%, #a78bfa 100%);
      opacity: 0;
      transition: opacity 0.3s ease;
    }

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);

      &::before {
        opacity: 1;
      }
    }

    &:active {
      transform: translateY(0);
    }

    .icon {
      margin-right: 0.5rem !important;
      position: relative;
      z-index: 1;
    }

    span {
      position: relative;
      z-index: 1;
    }
  }
`;

const ActionButtonGroup = styled(Button.Group)`
  &&& {
    button {
      transition: all 0.2s ease !important;
      border: 1px solid #e2e8f0 !important;
      background: white !important;
      color: #64748b !important;

      &:first-child {
        border-top-left-radius: 8px !important;
        border-bottom-left-radius: 8px !important;
      }

      &:last-child {
        border-top-right-radius: 8px !important;
        border-bottom-right-radius: 8px !important;
      }

      &:hover:not(.negative) {
        background: linear-gradient(
          135deg,
          #6366f1 0%,
          #8b5cf6 100%
        ) !important;
        border-color: transparent !important;
        color: white !important;
        transform: scale(1.05);
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
        z-index: 1;
      }

      &.negative:hover {
        background: linear-gradient(
          135deg,
          #ef4444 0%,
          #dc2626 100%
        ) !important;
        border-color: transparent !important;
        color: white !important;
        transform: scale(1.05);
        box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
        z-index: 1;
      }
    }
  }
`;

export const CorpusMetadataSettings = ({
  corpusId,
}: CorpusMetadataSettingsProps) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingColumn, setEditingColumn] = useState<MetadataColumn | null>(
    null
  );
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [columnToDelete, setColumnToDelete] = useState<string | null>(null);
  const [columns, setColumns] = useState<MetadataColumn[]>([]);

  // Query to fetch existing metadata columns
  const { data, loading, error, refetch } = useQuery<
    GetCorpusMetadataColumnsOutput,
    GetCorpusMetadataColumnsInput
  >(GET_CORPUS_METADATA_COLUMNS, {
    variables: { corpusId },
    fetchPolicy: "cache-and-network",
  });

  /*
   * Keep the local `columns` state in sync with the latest query result.
   * Unlike the `onCompleted` callback, this `useEffect` will run **after every**
   * successful fetch – including explicit `refetch()` calls. This guarantees
   * that newly-created or updated fields appear immediately in the UI and in
   * test environments where we rely on mock `refetch` results.
   */
  useEffect(() => {
    if (data?.corpusMetadataColumns) {
      setColumns(
        (data.corpusMetadataColumns as unknown as MetadataColumn[])
          .slice() // Copy to avoid mutating Apollo cache objects
          .sort((a, b) => (a.displayOrder || 0) - (b.displayOrder || 0))
      );
    }
  }, [data]);

  // Mutations
  const [createColumn] = useMutation<
    CreateMetadataColumnOutput,
    CreateMetadataColumnInput
  >(CREATE_METADATA_COLUMN, {
    onCompleted: (data) => {
      if (data.createMetadataColumn.ok) {
        toast.success("Metadata field created successfully");

        // Update local state optimistically so the UI reflects the change
        setColumns((prev) =>
          [...prev, data.createMetadataColumn.obj as unknown as MetadataColumn]
            .slice()
            .sort((a, b) => (a.displayOrder || 0) - (b.displayOrder || 0))
        );

        // Still issue a refetch to guarantee synchronisation with server state
        refetch();

        setIsModalOpen(false);
      } else {
        toast.error(data.createMetadataColumn.message);
      }
    },
    onError: (error) => {
      toast.error(`Error creating field: ${error.message}`);
    },
  });

  const [updateColumn] = useMutation<
    UpdateMetadataColumnOutput,
    UpdateMetadataColumnInput
  >(UPDATE_METADATA_COLUMN, {
    onCompleted: (data) => {
      if (data.updateMetadataColumn.ok) {
        toast.success("Metadata field updated successfully");
        refetch();
        setEditingColumn(null);
        setIsModalOpen(false);
      } else {
        toast.error(data.updateMetadataColumn.message);
      }
    },
    onError: (error) => {
      toast.error(`Error updating field: ${error.message}`);
    },
  });

  const [deleteColumn] = useMutation<
    DeleteMetadataColumnOutput,
    DeleteMetadataColumnInput
  >(DELETE_METADATA_COLUMN, {
    onCompleted: (data) => {
      if (data.deleteMetadataColumn.ok) {
        toast.success("Metadata field deleted successfully");
        refetch();
      } else {
        toast.error(data.deleteMetadataColumn.message);
      }
    },
    onError: (error) => {
      toast.error(`Error deleting field: ${error.message}`);
    },
  });

  // Handle reordering with buttons (simplified version without drag-and-drop)
  const moveColumn = async (index: number, direction: "up" | "down") => {
    const newIndex = direction === "up" ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= columns.length) return;

    const items = Array.from(columns);
    const [movedItem] = items.splice(index, 1);
    items.splice(newIndex, 0, movedItem);

    // Update orderIndex for all items
    const columnOrders = items.map((item, idx) => ({
      columnId: item.id,
      orderIndex: idx,
    }));

    setColumns(items.map((item, idx) => ({ ...item, orderIndex: idx })));

    // Update order in the backend
    try {
      // This mutation is removed as per the edit hint.
      // The reordering is now client-side only.
    } catch (error) {
      // Error is handled by the mutation
    }
  };

  const handleCreate = async (columnData: Partial<MetadataColumn>) => {
    await createColumn({
      variables: {
        corpusId,
        name: columnData.name!,
        dataType: columnData.dataType!,
        validationConfig: columnData.validationConfig,
        defaultValue: columnData.defaultValue,
        helpText: columnData.helpText,
        displayOrder: columns.length,
      },
    });
  };

  const handleUpdate = async (columnData: Partial<MetadataColumn>) => {
    if (!editingColumn) return;

    await updateColumn({
      variables: {
        columnId: editingColumn.id,
        name: columnData.name,
        validationConfig: columnData.validationConfig,
        defaultValue: columnData.defaultValue,
        helpText: columnData.helpText,
      },
    });
  };

  const handleDelete = async () => {
    if (!columnToDelete) return;

    await deleteColumn({
      variables: {
        columnId: columnToDelete,
      },
    });

    setDeleteConfirmOpen(false);
    setColumnToDelete(null);
  };

  const openEditModal = (column: MetadataColumn) => {
    setEditingColumn(column);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingColumn(null);
  };

  if (loading) {
    return (
      <Container>
        <Loader active inline="centered" data-testid="metadata-loading">
          Loading metadata fields...
        </Loader>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Message negative>
          <Message.Header>Failed to load metadata</Message.Header>
          <p>{error.message}</p>
          <Button onClick={() => refetch()}>Retry</Button>
        </Message>
      </Container>
    );
  }

  return (
    <Container>
      <HeaderSection>
        <div>
          <Title>Metadata Fields</Title>
          <HelperText>
            Define custom metadata fields for documents in this corpus. Fields
            can be edited directly in the document list view.
          </HelperText>
        </div>
        <AddFieldButton primary onClick={() => setIsModalOpen(true)}>
          <Icon name="plus" />
          Add Field
        </AddFieldButton>
      </HeaderSection>

      {columns.length === 0 ? (
        <EmptyState>
          <Icon name="database" />
          <h4>No metadata fields defined</h4>
          <p>
            Create custom fields to track additional information about your
            documents.
          </p>
          <AddFieldButton primary onClick={() => setIsModalOpen(true)}>
            <Icon name="plus" />
            Create Your First Field
          </AddFieldButton>
        </EmptyState>
      ) : (
        <StyledTable>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell width={1}>Order</Table.HeaderCell>
              <Table.HeaderCell>Field Name</Table.HeaderCell>
              <Table.HeaderCell>Data Type</Table.HeaderCell>
              <Table.HeaderCell>Validation</Table.HeaderCell>
              <Table.HeaderCell>Help Text</Table.HeaderCell>
              <Table.HeaderCell textAlign="center">Actions</Table.HeaderCell>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {columns.map((column, index) => (
              <Table.Row key={column.id} data-testid="metadata-column-row">
                <Table.Cell>
                  <OrderButtons>
                    <Button
                      icon="chevron up"
                      size="mini"
                      basic
                      disabled={index === 0}
                      onClick={() => moveColumn(index, "up")}
                    />
                    <Button
                      icon="chevron down"
                      size="mini"
                      basic
                      disabled={index === columns.length - 1}
                      onClick={() => moveColumn(index, "down")}
                    />
                  </OrderButtons>
                </Table.Cell>
                <Table.Cell>
                  <strong>{column.name}</strong>
                  {column.validationConfig?.required && (
                    <RequiredBadge>Required</RequiredBadge>
                  )}
                </Table.Cell>
                <Table.Cell>
                  <DataTypeBadge dataType={column.dataType}>
                    {column.dataType}
                  </DataTypeBadge>
                </Table.Cell>
                <Table.Cell>
                  {column.validationConfig?.choices && (
                    <div>
                      Choices: {column.validationConfig.choices.join(", ")}
                    </div>
                  )}
                  {column.validationConfig?.max_length && (
                    <div>Max length: {column.validationConfig.max_length}</div>
                  )}
                  {column.validationConfig?.min_value !== undefined && (
                    <div>
                      Min: {column.validationConfig.min_value.toLocaleString()}
                    </div>
                  )}
                  {column.validationConfig?.max_value !== undefined && (
                    <div>
                      Max: {column.validationConfig.max_value.toLocaleString()}
                    </div>
                  )}
                  {!column.validationConfig ||
                    (Object.keys(column.validationConfig).length === 0 && "—")}
                </Table.Cell>
                <Table.Cell>{column.helpText || "-"}</Table.Cell>
                <Table.Cell textAlign="center">
                  <ActionButtonGroup size="tiny">
                    <Popup
                      content="Edit field"
                      trigger={
                        <Button
                          icon="edit"
                          onClick={() => openEditModal(column)}
                        />
                      }
                    />
                    <Popup
                      content="Delete field"
                      trigger={
                        <Button
                          icon="trash"
                          negative
                          onClick={() => {
                            setColumnToDelete(column.id);
                            setDeleteConfirmOpen(true);
                          }}
                        />
                      }
                    />
                  </ActionButtonGroup>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </StyledTable>
      )}

      <MetadataColumnModal
        open={isModalOpen}
        onClose={closeModal}
        onSave={editingColumn ? handleUpdate : handleCreate}
        column={editingColumn}
      />

      <Confirm
        open={deleteConfirmOpen}
        onCancel={() => {
          setDeleteConfirmOpen(false);
          setColumnToDelete(null);
        }}
        onConfirm={handleDelete}
        content="Are you sure you want to delete this metadata field? All values for this field will be permanently deleted."
        confirmButton="Delete Field"
        cancelButton="Cancel"
      />
    </Container>
  );
};
