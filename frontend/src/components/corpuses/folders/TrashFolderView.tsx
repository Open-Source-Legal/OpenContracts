import React, { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation } from "@apollo/client";
import styled from "styled-components";
import {
  Button,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";
import {
  ErrorMessage,
  SuccessMessage,
  LoadingState,
} from "../../widgets/feedback";
import { formatDistanceToNow, format, isValid } from "date-fns";
import {
  Trash2,
  RotateCcw,
  Archive,
  FolderOpen,
  ArrowLeft,
  Undo2,
  AlertTriangle,
  Calendar,
  User,
  FileText,
  X,
} from "lucide-react";
import {
  GET_DELETED_DOCUMENTS_IN_CORPUS,
  DeletedDocumentPathType,
} from "../../../graphql/queries/folders";
import {
  RESTORE_DELETED_DOCUMENT,
  RestoreDeletedDocumentInput,
  RestoreDeletedDocumentOutput,
  EMPTY_TRASH,
  EmptyTrashInput,
  EmptyTrashOutput,
} from "../../../graphql/mutations";
import fallback_doc_icon from "../../../assets/images/defaults/default_doc_icon.jpg";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { getCreatorDisplay } from "../../../utils/userDisplay";

// Message auto-dismiss durations (in milliseconds)
const SUCCESS_MESSAGE_DURATION = 5000;
const ERROR_MESSAGE_DURATION = 10000;

/**
 * Safely format a date string to relative time (e.g., "2 hours ago").
 * Returns fallback text if date is invalid.
 */
const safeFormatDistanceToNow = (
  dateString: string | null | undefined
): string => {
  if (!dateString) return "Unknown time";
  try {
    const date = new Date(dateString);
    if (!isValid(date)) return "Unknown time";
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return "Unknown time";
  }
};

/**
 * Safely format a date string to a specific format.
 * Returns fallback text if date is invalid.
 */
const safeFormat = (
  dateString: string | null | undefined,
  formatString: string
): string => {
  if (!dateString) return "Unknown date";
  try {
    const date = new Date(dateString);
    if (!isValid(date)) return "Unknown date";
    return format(date, formatString);
  } catch {
    return "Unknown date";
  }
};

const Container = styled.div`
  padding: 20px;
  height: 100%;
  overflow-y: auto;

  @media (max-width: 480px) {
    padding: 12px;
  }
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  flex-wrap: wrap;
  gap: 8px;

  @media (max-width: 480px) {
    margin-bottom: 12px;
    padding-bottom: 8px;
  }
`;

const Title = styled.h2`
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #0f172a;
  font-size: 20px;
  font-weight: 600;

  svg {
    color: ${OS_LEGAL_COLORS.textSecondary};
    flex-shrink: 0;
  }

  @media (max-width: 480px) {
    font-size: 16px;
    gap: 6px;

    svg {
      width: 20px;
      height: 20px;
    }
  }
`;

const ActionBar = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;

  @media (max-width: 480px) {
    .ui.button {
      padding: 0.5em 0.8em;
      font-size: 12px;
    }

    /* Hide button text on mobile, show only icon */
    .ui.button .hide-mobile-text {
      display: none;
    }
  }
`;

const DocumentGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
    gap: 8px;
  }
`;

const DocumentCard = styled.div<{ $isSelected: boolean }>`
  background: white;
  border: 1px solid
    ${(props) =>
      props.$isSelected ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.textMuted};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  ${(props) =>
    props.$isSelected &&
    `
    background: ${OS_LEGAL_COLORS.blueSurface};
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  `}

  @media (max-width: 480px) {
    padding: 12px;
  }
`;

const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;

  @media (max-width: 480px) {
    gap: 10px;
    margin-bottom: 8px;
  }
`;

const Thumbnail = styled.div`
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  background: ${OS_LEGAL_COLORS.surfaceHover};
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

  @media (max-width: 480px) {
    width: 40px;
    height: 40px;

    .fallback-icon {
      width: 20px;
      height: 20px;
    }
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
    color: ${OS_LEGAL_COLORS.textSecondary};
    text-transform: uppercase;
    font-weight: 500;
  }
`;

const CardMeta = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
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

  /* Hide less important metadata on mobile */
  @media (max-width: 480px) {
    margin-bottom: 8px;

    .meta-row.hide-mobile {
      display: none;
    }
  }
`;

const CardActions = styled.div`
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid ${OS_LEGAL_COLORS.surfaceLight};

  @media (max-width: 480px) {
    padding-top: 8px;
  }
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 60px 20px;
  color: ${OS_LEGAL_COLORS.textSecondary};

  svg {
    margin-bottom: 16px;
    opacity: 0.3;
  }

  h3 {
    color: ${OS_LEGAL_COLORS.textTertiary};
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
  background: ${OS_LEGAL_COLORS.blueSurface};
  border: 1px solid ${OS_LEGAL_COLORS.primaryBlue};
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

  const [restoreDocument, { loading: restoreLoading }] = useMutation<
    RestoreDeletedDocumentOutput,
    RestoreDeletedDocumentInput
  >(RESTORE_DELETED_DOCUMENT, {
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
  });

  const [emptyTrash, { loading: emptyTrashLoading }] = useMutation<
    EmptyTrashOutput,
    EmptyTrashInput
  >(EMPTY_TRASH, {
    onCompleted: (data) => {
      if (data.emptyTrash.ok) {
        setRestoreSuccess(data.emptyTrash.message);
        setRestoreError(null);
        refetch();
        setSelectedDocuments(new Set());
      } else {
        setRestoreError(data.emptyTrash.message || "Failed to empty trash");
        setRestoreSuccess(null);
      }
      setConfirmEmptyTrash(false);
    },
    onError: (error) => {
      setRestoreError(error.message || "An unexpected error occurred");
      setRestoreSuccess(null);
      setConfirmEmptyTrash(false);
    },
  });

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
    // Filter out any documents with missing data
    const selectedDocs = deletedDocuments.filter((doc) =>
      selectedDocuments.has(doc.id)
    );
    const pathsToRestore = selectedDocs.filter((doc) => doc.document?.id);
    const skippedCount = selectedDocs.length - pathsToRestore.length;

    // Log skipped documents in development to help identify data integrity issues
    if (skippedCount > 0 && process.env.NODE_ENV === "development") {
      console.warn(
        "Skipped documents with null/missing data:",
        selectedDocs.filter((doc) => !doc.document?.id)
      );
    }

    if (pathsToRestore.length === 0) {
      setRestoreError(
        "Selected documents cannot be restored: document data is missing or corrupted"
      );
      return;
    }

    const results = await Promise.allSettled(
      pathsToRestore.map((docPath) =>
        restoreDocument({
          variables: {
            // Safe to use ! here since we filtered for doc.document?.id above
            documentId: docPath.document!.id,
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

    // Build skipped warning message if any documents were filtered
    const skippedWarning =
      skippedCount > 0
        ? `${skippedCount} document${
            skippedCount === 1 ? "" : "s"
          } skipped: missing or corrupted data`
        : null;

    // Set appropriate messages
    if (successCount > 0 && failureCount === 0) {
      setRestoreSuccess(
        `Successfully restored ${successCount} document${
          successCount === 1 ? "" : "s"
        }`
      );
      // Show skipped warning if any documents were skipped
      if (skippedWarning) {
        setRestoreError(skippedWarning);
      }
    } else if (successCount > 0 && failureCount > 0) {
      setRestoreSuccess(
        `Restored ${successCount} document${successCount === 1 ? "" : "s"}`
      );
      // Combine failure and skipped messages
      const failureMsg = `Failed to restore ${failureCount} document${
        failureCount === 1 ? "" : "s"
      }. Please try again.`;
      setRestoreError(
        skippedWarning ? `${failureMsg} ${skippedWarning}` : failureMsg
      );
    } else if (failureCount > 0) {
      const failureMsg = `Failed to restore ${failureCount} document${
        failureCount === 1 ? "" : "s"
      }. Please check permissions and try again.`;
      setRestoreError(
        skippedWarning ? `${failureMsg} ${skippedWarning}` : failureMsg
      );
    } else if (skippedWarning) {
      // All documents were skipped (shouldn't happen since we check pathsToRestore.length above)
      setRestoreError(skippedWarning);
    }
  };

  const handleRestoreSingle = (docPath: DeletedDocumentPathType) => {
    if (!docPath.document?.id) {
      setRestoreError("Cannot restore: document information is missing");
      return;
    }
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
    (doc: NonNullable<DeletedDocumentPathType["document"]>) => (
      <Thumbnail>
        {doc.icon ? (
          <img src={doc.icon} alt={doc.title} />
        ) : (
          <>
            <div
              style={{
                width: "100%",
                height: "100%",
                background: OS_LEGAL_COLORS.surfaceHover,
              }}
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

  // Auto-dismiss success messages
  useEffect(() => {
    if (restoreSuccess) {
      const timer = setTimeout(
        () => setRestoreSuccess(null),
        SUCCESS_MESSAGE_DURATION
      );
      return () => clearTimeout(timer);
    }
  }, [restoreSuccess]);

  // Auto-dismiss error messages
  useEffect(() => {
    if (restoreError) {
      const timer = setTimeout(
        () => setRestoreError(null),
        ERROR_MESSAGE_DURATION
      );
      return () => clearTimeout(timer);
    }
  }, [restoreError]);

  if (loading && !data) {
    return (
      <Container>
        <LoadingState message="Loading trash..." size="lg" />
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <ErrorMessage title="Failed to load trash">
          {error.message}
        </ErrorMessage>
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
                color: OS_LEGAL_COLORS.textSecondary,
              }}
            >
              ({deletedDocuments.length}{" "}
              {deletedDocuments.length === 1 ? "item" : "items"})
            </span>
          )}
        </Title>
        <ActionBar>
          {onBack && (
            <Button
              variant="secondary"
              onClick={onBack}
              leftIcon={<ArrowLeft size={16} />}
              title="Back to Folders"
            >
              <span className="hide-mobile-text">Back</span>
            </Button>
          )}
          {deletedDocuments.length > 0 && (
            <Button
              variant="secondary"
              onClick={() => setConfirmEmptyTrash(true)}
              disabled={emptyTrashLoading}
              loading={emptyTrashLoading}
              leftIcon={<Trash2 size={16} />}
              title="Permanently delete all items in trash"
              style={{
                color: OS_LEGAL_COLORS.danger,
                borderColor: OS_LEGAL_COLORS.danger,
              }}
            >
              <span className="hide-mobile-text">Empty Trash</span>
            </Button>
          )}
        </ActionBar>
      </Header>

      {restoreSuccess && (
        <div
          style={{
            marginBottom: "16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "0.5rem",
          }}
        >
          <SuccessMessage title="Success" style={{ flex: 1 }}>
            {restoreSuccess}
          </SuccessMessage>
          <button
            onClick={() => setRestoreSuccess(null)}
            aria-label="Dismiss"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: OS_LEGAL_COLORS.successText,
              padding: "0.75rem 0.25rem 0",
              display: "flex",
              alignItems: "center",
            }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {restoreError && (
        <div
          style={{
            marginBottom: "16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "0.5rem",
          }}
        >
          <ErrorMessage title="Restore Failed" style={{ flex: 1 }}>
            {restoreError}
          </ErrorMessage>
          <button
            onClick={() => setRestoreError(null)}
            aria-label="Dismiss"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: OS_LEGAL_COLORS.dangerText,
              padding: "0.75rem 0.25rem 0",
              display: "flex",
              alignItems: "center",
            }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {selectedDocuments.size > 0 && (
        <SelectionBar>
          <div className="selection-info">
            {selectedDocuments.size}{" "}
            {selectedDocuments.size === 1 ? "item" : "items"} selected
          </div>
          <div className="selection-actions">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSelectedDocuments(new Set())}
            >
              Clear Selection
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleRestoreSelected}
              loading={restoreLoading}
              disabled={restoreLoading}
              leftIcon={<Undo2 size={14} />}
            >
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
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={selectedDocuments.size === deletedDocuments.length}
                ref={(el) => {
                  if (el) {
                    el.indeterminate =
                      selectedDocuments.size > 0 &&
                      selectedDocuments.size < deletedDocuments.length;
                  }
                }}
                onChange={handleSelectAll}
              />
              Select all
            </label>
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
                    {docPath.document ? (
                      renderThumbnail(docPath.document)
                    ) : (
                      <Thumbnail>
                        <div
                          style={{
                            width: "100%",
                            height: "100%",
                            background: OS_LEGAL_COLORS.surfaceHover,
                          }}
                        />
                        <img
                          src={fallback_doc_icon}
                          alt="Document"
                          className="fallback-icon"
                        />
                      </Thumbnail>
                    )}
                    <CardTitle>
                      <h4>{docPath.document?.title || "Untitled Document"}</h4>
                      <span className="file-type">
                        {docPath.document?.fileType || "Unknown"}
                      </span>
                    </CardTitle>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => handleSelectDocument(docPath.id)}
                    />
                  </CardHeader>

                  <CardMeta>
                    <div className="meta-row">
                      <Trash2 size={12} className="icon" />
                      Deleted {safeFormatDistanceToNow(docPath.modified)}
                    </div>
                    <div className="meta-row hide-mobile">
                      <Calendar size={12} className="icon" />
                      {safeFormat(docPath.modified, "MMM d, yyyy h:mm a")}
                    </div>
                    <div className="meta-row hide-mobile">
                      <User size={12} className="icon" />
                      Deleted by {getCreatorDisplay(docPath.creator)}
                    </div>
                    {docPath.folder && (
                      <div className="meta-row hide-mobile">
                        <FolderOpen size={12} className="icon" />
                        Was in: {docPath.folder.name}
                      </div>
                    )}
                    <div className="meta-row">
                      <FileText size={12} className="icon" />
                      {docPath.document?.pageCount || 0} pages
                    </div>
                  </CardMeta>

                  <CardActions>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={(e: React.MouseEvent) => {
                        e.stopPropagation();
                        handleRestoreSingle(docPath);
                      }}
                      loading={restoreLoading}
                      disabled={restoreLoading}
                      leftIcon={<RotateCcw size={14} />}
                      style={{ width: "100%" }}
                    >
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
        size="sm"
        open={confirmEmptyTrash}
        onClose={() => setConfirmEmptyTrash(false)}
      >
        <ModalHeader
          title="Empty Trash - Permanent Deletion"
          onClose={() => setConfirmEmptyTrash(false)}
        />
        <ModalBody>
          <ErrorMessage title="This action cannot be undone!">
            <>
              You are about to permanently delete{" "}
              <strong>{deletedDocuments.length}</strong>{" "}
              {deletedDocuments.length === 1 ? "document" : "documents"} from
              the trash. This will remove:
              <ul>
                <li>All document history and versions in this corpus</li>
                <li>All annotations you created on these documents</li>
                <li>All relationships involving those annotations</li>
                <li>All document summary revisions</li>
              </ul>
              <strong>
                Documents that exist in other corpuses will NOT be affected.
              </strong>
            </>
          </ErrorMessage>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setConfirmEmptyTrash(false)}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={emptyTrashLoading}
            disabled={emptyTrashLoading}
            onClick={() => {
              emptyTrash({
                variables: { corpusId },
              });
            }}
            leftIcon={<Trash2 size={14} />}
          >
            Permanently Delete All
          </Button>
        </ModalFooter>
      </Modal>
    </Container>
  );
};

export default TrashFolderView;
