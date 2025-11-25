import React, { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation } from "@apollo/client";
import styled from "styled-components";
import {
  Icon,
  Button,
  Loader,
  Message,
  Checkbox,
  Modal,
} from "semantic-ui-react";
import { formatDistanceToNow, format } from "date-fns";
import { Trash2, RotateCcw, Archive, FolderOpen } from "lucide-react";
import {
  GET_DELETED_DOCUMENTS_IN_CORPUS,
  DeletedDocumentPathType,
} from "../../../graphql/queries/folders";
import { RESTORE_DELETED_DOCUMENT } from "../../../graphql/mutations";
import fallback_doc_icon from "../../../assets/images/defaults/default_doc_icon.jpg";

const Container = styled.div`
  padding: 20px;
  height: 100%;
  overflow-y: auto;
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e2e8f0;
`;

const Title = styled.h2`
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  color: #0f172a;
  font-size: 24px;
  font-weight: 600;

  svg {
    color: #64748b;
  }
`;

const ActionBar = styled.div`
  display: flex;
  gap: 12px;
  align-items: center;
`;

const DocumentGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
`;

const DocumentCard = styled.div<{ $isSelected: boolean }>`
  background: white;
  border: 1px solid ${(props) => (props.$isSelected ? "#3b82f6" : "#e2e8f0")};
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    border-color: #94a3b8;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  ${(props) =>
    props.$isSelected &&
    `
    background: #eff6ff;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  `}
`;

const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
`;

const Thumbnail = styled.div`
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  background: #f8fafc;
  flex-shrink: 0;
  position: relative;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fallback-icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 24px;
    height: 24px;
    opacity: 0.2;
  }
`;

const CardTitle = styled.div`
  flex: 1;
  min-width: 0;

  h4 {
    margin: 0 0 4px;
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-type {
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 500;
  }
`;

const CardMeta = styled.div`
  font-size: 12px;
  color: #64748b;
  margin-bottom: 12px;

  .meta-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  .icon {
    font-size: 11px;
    opacity: 0.7;
  }
`;

const CardActions = styled.div`
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 60px 20px;
  color: #64748b;

  svg {
    margin-bottom: 16px;
    opacity: 0.3;
  }

  h3 {
    color: #475569;
    margin-bottom: 8px;
    font-size: 18px;
  }

  p {
    font-size: 14px;
    max-width: 400px;
    margin: 0 auto;
  }
`;

const SelectionBar = styled.div`
  background: #eff6ff;
  border: 1px solid #3b82f6;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;

  .selection-info {
    font-weight: 500;
    color: #1d4ed8;
  }

  .selection-actions {
    display: flex;
    gap: 8px;
  }
`;

interface TrashFolderViewProps {
  corpusId: string;
  onBack?: () => void;
}

export const TrashFolderView: React.FC<TrashFolderViewProps> = ({
  corpusId,
  onBack,
}) => {
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(
    new Set()
  );
  const [restoreSuccess, setRestoreSuccess] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [confirmEmptyTrash, setConfirmEmptyTrash] = useState(false);

  const { data, loading, error, refetch } = useQuery(
    GET_DELETED_DOCUMENTS_IN_CORPUS,
    {
      variables: { corpusId },
      fetchPolicy: "cache-and-network",
    }
  );

  const [restoreDocument, { loading: restoreLoading }] = useMutation(
    RESTORE_DELETED_DOCUMENT,
    {
      onCompleted: (data) => {
        if (data.restoreDeletedDocument.ok) {
          setRestoreSuccess("Document restored successfully");
          setRestoreError(null);
          refetch();
          setSelectedDocuments(new Set());
        } else {
          setRestoreError(
            data.restoreDeletedDocument.message || "Failed to restore document"
          );
          setRestoreSuccess(null);
        }
      },
      onError: (error) => {
        setRestoreError(error.message || "An unexpected error occurred");
        setRestoreSuccess(null);
      },
    }
  );

  const deletedDocuments: DeletedDocumentPathType[] =
    data?.deletedDocumentsInCorpus || [];

  const handleSelectDocument = (pathId: string) => {
    setSelectedDocuments((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(pathId)) {
        newSet.delete(pathId);
      } else {
        newSet.add(pathId);
      }
      return newSet;
    });
  };

  const handleSelectAll = () => {
    if (selectedDocuments.size === deletedDocuments.length) {
      setSelectedDocuments(new Set());
    } else {
      setSelectedDocuments(new Set(deletedDocuments.map((doc) => doc.id)));
    }
  };

  const handleRestoreSelected = async () => {
    setRestoreError(null);
    setRestoreSuccess(null);

    // Restore each selected document using Promise.allSettled for better error handling
    const pathsToRestore = deletedDocuments.filter((doc) =>
      selectedDocuments.has(doc.id)
    );

    const results = await Promise.allSettled(
      pathsToRestore.map((docPath) =>
        restoreDocument({
          variables: {
            documentId: docPath.document.id,
            corpusId: corpusId,
          },
        })
      )
    );

    // Count successes and failures
    const successCount = results.filter(
      (r) =>
        r.status === "fulfilled" && r.value.data?.restoreDeletedDocument?.ok
    ).length;
    const failureCount = results.length - successCount;

    // Clear only successfully restored documents from selection
    if (successCount > 0) {
      const successfulIds = new Set<string>();
      results.forEach((result, index) => {
        if (
          result.status === "fulfilled" &&
          result.value.data?.restoreDeletedDocument?.ok
        ) {
          successfulIds.add(pathsToRestore[index].id);
        }
      });
      setSelectedDocuments(
        (prev) => new Set([...prev].filter((id) => !successfulIds.has(id)))
      );
      refetch();
    }

    // Set appropriate messages
    if (successCount > 0 && failureCount === 0) {
      setRestoreSuccess(
        `Successfully restored ${successCount} document${
          successCount === 1 ? "" : "s"
        }`
      );
    } else if (successCount > 0 && failureCount > 0) {
      setRestoreSuccess(
        `Restored ${successCount} document${successCount === 1 ? "" : "s"}`
      );
      setRestoreError(
        `Failed to restore ${failureCount} document${
          failureCount === 1 ? "" : "s"
        }. Please try again.`
      );
    } else if (failureCount > 0) {
      setRestoreError(
        `Failed to restore ${failureCount} document${
          failureCount === 1 ? "" : "s"
        }. Please check permissions and try again.`
      );
    }
  };

  const handleRestoreSingle = (docPath: DeletedDocumentPathType) => {
    setRestoreError(null);
    setRestoreSuccess(null);
    restoreDocument({
      variables: {
        documentId: docPath.document.id,
        corpusId: corpusId,
      },
    });
  };

  const renderThumbnail = useCallback(
    (doc: DeletedDocumentPathType["document"]) => (
      <Thumbnail>
        {doc.icon ? (
          <img src={doc.icon} alt={doc.title} />
        ) : (
          <>
            <div
              style={{ width: "100%", height: "100%", background: "#f8fafc" }}
            />
            <img
              src={fallback_doc_icon}
              alt="Document"
              className="fallback-icon"
            />
          </>
        )}
      </Thumbnail>
    ),
    []
  );

  // Auto-dismiss success messages after 5 seconds
  useEffect(() => {
    if (restoreSuccess) {
      const timer = setTimeout(() => setRestoreSuccess(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [restoreSuccess]);

  // Auto-dismiss error messages after 10 seconds
  useEffect(() => {
    if (restoreError) {
      const timer = setTimeout(() => setRestoreError(null), 10000);
      return () => clearTimeout(timer);
    }
  }, [restoreError]);

  if (loading && !data) {
    return (
      <Container>
        <div style={{ textAlign: "center", padding: "60px 20px" }}>
          <Loader active inline="centered" size="large">
            Loading trash...
          </Loader>
        </div>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Message negative>
          <Message.Header>Failed to load trash</Message.Header>
          <p>{error.message}</p>
        </Message>
      </Container>
    );
  }

  return (
    <Container>
      <Header>
        <Title>
          <Trash2 size={28} />
          Trash
          {deletedDocuments.length > 0 && (
            <span
              style={{
                fontSize: "16px",
                fontWeight: "normal",
                color: "#64748b",
              }}
            >
              ({deletedDocuments.length}{" "}
              {deletedDocuments.length === 1 ? "item" : "items"})
            </span>
          )}
        </Title>
        <ActionBar>
          {onBack && (
            <Button basic onClick={onBack}>
              <Icon name="arrow left" />
              Back to Folders
            </Button>
          )}
          {deletedDocuments.length > 0 && (
            <Button
              basic
              color="red"
              onClick={() => setConfirmEmptyTrash(true)}
              disabled={true} // Permanent deletion not yet implemented
              title="Permanent deletion feature coming soon"
            >
              <Icon name="trash" />
              Empty Trash
            </Button>
          )}
        </ActionBar>
      </Header>

      {restoreSuccess && (
        <Message
          positive
          onDismiss={() => setRestoreSuccess(null)}
          style={{ marginBottom: "16px" }}
        >
          <Message.Header>Success</Message.Header>
          <p>{restoreSuccess}</p>
        </Message>
      )}

      {restoreError && (
        <Message
          negative
          onDismiss={() => setRestoreError(null)}
          style={{ marginBottom: "16px" }}
        >
          <Message.Header>Restore Failed</Message.Header>
          <p>{restoreError}</p>
        </Message>
      )}

      {selectedDocuments.size > 0 && (
        <SelectionBar>
          <div className="selection-info">
            {selectedDocuments.size}{" "}
            {selectedDocuments.size === 1 ? "item" : "items"} selected
          </div>
          <div className="selection-actions">
            <Button
              basic
              size="small"
              onClick={() => setSelectedDocuments(new Set())}
            >
              Clear Selection
            </Button>
            <Button
              primary
              size="small"
              onClick={handleRestoreSelected}
              loading={restoreLoading}
              disabled={restoreLoading}
            >
              <Icon name="undo" />
              Restore Selected
            </Button>
          </div>
        </SelectionBar>
      )}

      {deletedDocuments.length === 0 ? (
        <EmptyState>
          <Archive size={64} />
          <h3>Trash is Empty</h3>
          <p>
            Deleted documents will appear here. You can restore them or
            permanently delete them.
          </p>
        </EmptyState>
      ) : (
        <>
          <div
            style={{
              marginBottom: "16px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <Checkbox
              label="Select all"
              checked={selectedDocuments.size === deletedDocuments.length}
              indeterminate={
                selectedDocuments.size > 0 &&
                selectedDocuments.size < deletedDocuments.length
              }
              onChange={handleSelectAll}
            />
          </div>

          <DocumentGrid>
            {deletedDocuments.map((docPath) => {
              const isSelected = selectedDocuments.has(docPath.id);
              return (
                <DocumentCard
                  key={docPath.id}
                  $isSelected={isSelected}
                  onClick={() => handleSelectDocument(docPath.id)}
                >
                  <CardHeader>
                    {renderThumbnail(docPath.document)}
                    <CardTitle>
                      <h4>{docPath.document.title || "Untitled Document"}</h4>
                      <span className="file-type">
                        {docPath.document.fileType || "Unknown"}
                      </span>
                    </CardTitle>
                    <Checkbox
                      checked={isSelected}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => handleSelectDocument(docPath.id)}
                    />
                  </CardHeader>

                  <CardMeta>
                    <div className="meta-row">
                      <Icon name="trash" className="icon" />
                      Deleted{" "}
                      {formatDistanceToNow(new Date(docPath.modified), {
                        addSuffix: true,
                      })}
                    </div>
                    <div className="meta-row">
                      <Icon name="calendar" className="icon" />
                      {format(new Date(docPath.modified), "MMM d, yyyy h:mm a")}
                    </div>
                    <div className="meta-row">
                      <Icon name="user" className="icon" />
                      Deleted by {docPath.createdBy.username}
                    </div>
                    {docPath.folder && (
                      <div className="meta-row">
                        <FolderOpen size={12} className="icon" />
                        Was in: {docPath.folder.name}
                      </div>
                    )}
                    <div className="meta-row">
                      <Icon name="file outline" className="icon" />
                      {docPath.document.pageCount || 0} pages
                    </div>
                  </CardMeta>

                  <CardActions>
                    <Button
                      primary
                      size="tiny"
                      fluid
                      onClick={(e: React.MouseEvent) => {
                        e.stopPropagation();
                        handleRestoreSingle(docPath);
                      }}
                      loading={restoreLoading}
                      disabled={restoreLoading}
                    >
                      <RotateCcw size={14} style={{ marginRight: "6px" }} />
                      Restore
                    </Button>
                  </CardActions>
                </DocumentCard>
              );
            })}
          </DocumentGrid>
        </>
      )}

      <Modal
        size="tiny"
        open={confirmEmptyTrash}
        onClose={() => setConfirmEmptyTrash(false)}
      >
        <Modal.Header>Empty Trash</Modal.Header>
        <Modal.Content>
          <Message warning>
            <Message.Header>Feature Not Yet Available</Message.Header>
            <p>
              Permanent deletion of documents is not yet implemented. Documents
              in the trash can be restored but cannot be permanently deleted at
              this time.
            </p>
          </Message>
          <p>
            <strong>Planned Behavior:</strong> This will permanently delete all{" "}
            {deletedDocuments.length} documents in the trash. This action cannot
            be undone.
          </p>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setConfirmEmptyTrash(false)}>Close</Button>
        </Modal.Actions>
      </Modal>
    </Container>
  );
};

export default TrashFolderView;
