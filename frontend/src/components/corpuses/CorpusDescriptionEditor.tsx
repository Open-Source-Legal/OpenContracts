import React, { useState, useEffect, useCallback, useRef } from "react";
import { Modal, Header } from "semantic-ui-react";
import { Button } from "@os-legal/ui";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery } from "@apollo/client";
import { toast } from "react-toastify";
import {
  Clock,
  Save,
  X,
  History,
  Edit3,
  ChevronLeft,
  User,
  FileText,
  GitBranch,
  Check,
  AlertCircle,
  RotateCcw,
  Eye,
  Edit,
  Copy,
  BookOpen,
  Info,
} from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import {
  UPDATE_CORPUS_DESCRIPTION,
  UpdateCorpusDescriptionInputs,
  UpdateCorpusDescriptionOutputs,
} from "../../graphql/mutations";
import {
  GET_CORPUS_WITH_HISTORY,
  GetCorpusWithHistoryQuery,
  GetCorpusWithHistoryQueryVariables,
  CorpusRevision,
} from "../../graphql/queries";
import { SafeMarkdown } from "../knowledge_base/markdown/SafeMarkdown";

// Styled Components
const StyledModal = styled(Modal)`
  &&& {
    width: 90vw;
    max-width: 1200px;
    height: 85vh !important;
    max-height: 85vh !important;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    display: flex;
    flex-direction: column;
    margin: 7.5vh auto;

    /* Override Semantic UI defaults */
    & > .content {
      flex: 1;
      overflow: hidden;
      padding: 0;
      max-height: none;
    }

    @media (max-width: 768px) {
      width: 100vw;
      height: 100vh !important;
      max-height: 100vh !important;
      margin: 0;
      border-radius: 0;
    }
  }
`;

const ModalHeader = styled(Modal.Header)`
  &&& {
    padding: 1.5rem 2rem !important;
    background: white;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    min-height: 60px;
    max-height: 60px;

    @media (max-width: 768px) {
      padding: 1rem !important;
      min-height: auto;
      max-height: none;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
  }
`;

const ModalContent = styled(Modal.Content)`
  &&& {
    display: flex !important;
    padding: 0 !important;
    flex: 1 !important;
    overflow: hidden !important;
    background: #f8fafc;
    min-height: 0 !important;
    max-height: calc(85vh - 60px - 70px) !important;
    position: relative;
    height: 100%;

    @media (max-width: 768px) {
      max-height: none !important;
      overflow-y: auto !important;
      overflow-x: hidden !important;
    }
  }
`;

const ContentWrapper = styled.div`
  display: flex;
  width: 100%;
  height: calc(85vh - 60px - 70px);
  max-height: calc(85vh - 60px - 70px);
  overflow: hidden;
  position: relative;

  @media (max-width: 768px) {
    flex-direction: column;
    height: auto;
    max-height: none;
    overflow: visible;
  }
`;

const EditorContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 8px;
  margin: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  flex-shrink: 1;

  @media (max-width: 768px) {
    margin: 0.5rem;
    border-radius: 0;
    overflow: visible;
    max-height: none;
    flex: none;
  }
`;

const EditorHeader = styled.div`
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: linear-gradient(to right, #f8fafc, #f1f5f9);
  flex-shrink: 0;

  h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1.5rem;
    color: #1e293b;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .meta {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    color: #64748b;
    font-size: 0.875rem;
    flex-wrap: wrap;

    .meta-item {
      display: flex;
      align-items: center;
      gap: 0.375rem;
    }
  }

  @media (max-width: 768px) {
    padding: 0.75rem;

    h3 {
      font-size: 1.125rem;
    }

    .meta {
      gap: 0.75rem;
      font-size: 0.75rem;
    }
  }
`;

const EditorWrapper = styled.div`
  flex: 1;
  display: flex;
  padding: 1.5rem;
  gap: 1.5rem;
  overflow: hidden;
  min-height: 0;
  max-height: 100%;
  min-width: 0;

  @media (max-width: 768px) {
    flex-direction: column;
    padding: 0.75rem;
    gap: 0.75rem;
    overflow: visible;
    flex: none;
    max-height: none;
  }
`;

const Editor = styled.textarea`
  flex: 1;
  padding: 1.5rem;
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  border: 2px solid #e2e8f0;
  border-radius: 8px;
  resize: none;
  background: #fafbfc;
  color: #1e293b;
  transition: all 0.2s;
  overflow-y: auto;
  min-height: 0;
  min-width: 0;
  flex-shrink: 1;

  &:focus {
    outline: none;
    border-color: #4a90e2;
    background: white;
    box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
  }

  &::placeholder {
    color: #94a3b8;
  }

  @media (max-width: 768px) {
    padding: 0.75rem;
    font-size: 0.8125rem;
    min-height: 200px;
    max-height: 300px;
    resize: none;
    flex: none;
  }
`;

const Preview = styled.div`
  flex: 1;
  padding: 1.5rem;
  border: 2px solid #e2e8f0;
  border-radius: 8px;
  background: white;
  overflow-y: auto;
  min-height: 0;
  min-width: 0;
  flex-shrink: 1;

  word-wrap: break-word;
  overflow-wrap: break-word;

  @media (max-width: 768px) {
    padding: 0.75rem;
    min-height: 200px;
    max-height: 300px;
    flex: none;
  }
`;

const HistoryPanel = styled(motion.div)`
  width: min(400px, 40vw);
  background: white;
  border-left: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  flex-shrink: 0;

  @media (max-width: 768px) {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100%;
    height: 100vh;
    z-index: 1001;
    border-left: none;
    border-top: none;
    max-height: none;
  }
`;

const HistoryHeader = styled.div`
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: linear-gradient(to right, #f8fafc, #f1f5f9);
  flex-shrink: 0;
  position: relative;

  h4 {
    margin: 0;
    font-size: 1.125rem;
    color: #1e293b;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .version-count {
    margin-top: 0.375rem;
    font-size: 0.875rem;
    color: #64748b;
  }

  .header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }

  .header-info {
    flex: 1;
  }

  @media (max-width: 768px) {
    padding: 1rem;

    h4 {
      font-size: 1rem;
    }

    .version-count {
      font-size: 0.75rem;
    }
  }
`;

const MobileHistoryCloseButton = styled.button`
  display: none;

  @media (max-width: 768px) {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: none;
    background: white;
    border-radius: 8px;
    cursor: pointer;
    color: #64748b;
    transition: all 0.2s;
    flex-shrink: 0;

    &:hover {
      background: #f1f5f9;
      color: #1e293b;
    }

    &:active {
      transform: scale(0.95);
    }
  }
`;

const HistoryBackdrop = styled(motion.div)`
  display: none;

  @media (max-width: 768px) {
    display: block;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 1000;
  }
`;

const HistoryList = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0.5rem;
  min-height: 0;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;

    &:hover {
      background: #94a3b8;
    }
  }
`;

const VersionDetails = styled(motion.div)`
  padding: 1rem;
  margin: 0.5rem;
  background: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  overflow: hidden;

  .version-content {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e0e7ff;
    border-radius: 6px;
    font-size: 0.875rem;
    max-height: 200px;
    overflow-y: auto;
    overflow-x: hidden;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  .version-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
    flex-wrap: wrap;
  }

  @media (max-width: 768px) {
    padding: 0.75rem;
    margin: 0.25rem;

    .version-content {
      padding: 0.5rem;
      font-size: 0.8125rem;
      max-height: 150px;
    }

    .version-actions {
      flex-direction: column;

      button {
        width: 100%;
      }
    }
  }
`;

interface VersionItemProps {
  $isActive?: boolean;
  $isViewing?: boolean;
}

const VersionItem = styled(motion.button)<VersionItemProps>`
  width: 100%;
  padding: 1rem;
  border: 1px solid
    ${(props) =>
      props.$isActive ? "#4a90e2" : props.$isViewing ? "#a78bfa" : "#e2e8f0"};
  border-radius: 8px;
  background: ${(props) =>
    props.$isActive ? "#eff6ff" : props.$isViewing ? "#f3f4f6" : "white"};
  text-align: left;
  cursor: pointer;
  margin-bottom: 0.5rem;
  transition: all 0.2s;

  &:hover {
    border-color: ${(props) => (props.$isActive ? "#4a90e2" : "#a78bfa")};
    background: ${(props) => (props.$isActive ? "#eff6ff" : "#f9fafb")};
    transform: translateX(2px);
  }

  .version-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;

    .version-number {
      font-weight: 600;
      color: ${(props) =>
        props.$isActive ? "#4a90e2" : props.$isViewing ? "#7c3aed" : "#1e293b"};
      display: flex;
      align-items: center;
      gap: 0.375rem;
    }

    .version-badge {
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      background: ${(props) =>
        props.$isActive ? "#4a90e2" : props.$isViewing ? "#a78bfa" : "#e2e8f0"};
      color: ${(props) =>
        props.$isActive || props.$isViewing ? "white" : "#64748b"};
    }
  }

  .version-meta {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8125rem;
    color: #64748b;

    .meta-row {
      display: flex;
      align-items: center;
      gap: 0.375rem;
    }
  }

  @media (max-width: 768px) {
    padding: 0.75rem;

    .version-header {
      .version-number {
        font-size: 0.875rem;
      }

      .version-badge {
        font-size: 0.6875rem;
        padding: 0.125rem 0.375rem;
      }
    }

    .version-meta {
      font-size: 0.75rem;
    }
  }
`;

const ActionBar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
  flex-shrink: 0;
  min-width: 0;
  gap: 1rem;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    padding: 0.75rem;
    gap: 0.75rem;
    position: sticky;
    bottom: 0;
    z-index: 10;
    box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.1);
  }
`;

const ActionGroup = styled.div`
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  min-width: 0;
  flex-shrink: 1;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: center;
  }
`;

interface StyledButtonWrapperProps {
  $variant?: "primary" | "secondary" | "danger" | "success";
  $size?: "small" | "medium";
}

const StyledButtonWrapper = styled.div<StyledButtonWrapperProps>`
  display: inline-block;

  button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: ${(props) =>
      props.$size === "small" ? "0.5rem 1rem" : "0.625rem 1.25rem"};
    border-radius: 8px;
    font-weight: 500;
    font-size: ${(props) =>
      props.$size === "small" ? "0.8125rem" : "0.875rem"};
    transition: all 0.2s;
    white-space: nowrap;
    flex-shrink: 0;

    ${(props) =>
      props.$variant === "primary" &&
      `
      background: #4a90e2 !important;
      color: white !important;
      &:hover {
        background: #357abd !important;
        transform: translateY(-1px);
      }
    `}

    ${(props) =>
      props.$variant === "secondary" &&
      `
      background: white !important;
      color: #64748b !important;
      border: 1px solid #e2e8f0 !important;
      &:hover {
        background: #f8fafc !important;
        border-color: #cbd5e1 !important;
      }
    `}

    ${(props) =>
      props.$variant === "success" &&
      `
      background: #10b981 !important;
      color: white !important;
      &:hover {
        background: #059669 !important;
        transform: translateY(-1px);
      }
    `}

    ${(props) =>
      props.$variant === "danger" &&
      `
      background: white !important;
      color: #ef4444 !important;
      border: 1px solid #fecaca !important;
      &:hover {
        background: #fef2f2 !important;
        border-color: #f87171 !important;
      }
    `}

    @media (max-width: 768px) {
      flex: 1;
      justify-content: center;
      min-width: auto;
      font-size: 0.8125rem;
      padding: 0.5rem 0.75rem;
    }
  }
`;

interface StyledButtonProps {
  $variant?: "primary" | "secondary" | "danger" | "success";
  $size?: "small" | "medium";
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  children: React.ReactNode;
}

const StyledButton: React.FC<StyledButtonProps> = ({
  $variant,
  $size,
  onClick,
  disabled,
  loading,
  children,
}) => (
  <StyledButtonWrapper $variant={$variant} $size={$size}>
    <Button onClick={onClick} disabled={disabled} loading={loading}>
      {children}
    </Button>
  </StyledButtonWrapper>
);

const EditingIndicator = styled(motion.div)`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  background: #fef3c7;
  color: #92400e;
  border-radius: 9999px;
  font-size: 0.8125rem;
  font-weight: 500;
  margin-left: 0.5rem;
  flex-shrink: 1;
  min-width: 0;

  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;

  @media (max-width: 768px) {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
    margin-left: 0.25rem;
    max-width: 150px;
  }
`;

interface CorpusDescriptionEditorProps {
  corpusId: string;
  isOpen: boolean;
  onClose: () => void;
  onUpdate?: () => void;
}

export const CorpusDescriptionEditor: React.FC<
  CorpusDescriptionEditorProps
> = ({ corpusId, isOpen, onClose, onUpdate }) => {
  const [content, setContent] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [viewingVersion, setViewingVersion] = useState<CorpusRevision | null>(
    null
  );
  const [editingFromVersion, setEditingFromVersion] = useState<number | null>(
    null
  );
  const [hasChanges, setHasChanges] = useState(false);
  const [currentContent, setCurrentContent] = useState("");

  // GraphQL hooks
  const { data, loading, refetch } = useQuery<
    GetCorpusWithHistoryQuery,
    GetCorpusWithHistoryQueryVariables
  >(GET_CORPUS_WITH_HISTORY, {
    variables: { id: corpusId },
    skip: !isOpen,
  });

  const [updateDescription, { loading: updating }] = useMutation<
    UpdateCorpusDescriptionOutputs,
    UpdateCorpusDescriptionInputs
  >(UPDATE_CORPUS_DESCRIPTION);

  // Fetch current content from mdDescription URL when data loads
  useEffect(() => {
    if (data?.corpus?.mdDescription) {
      fetch(data.corpus.mdDescription)
        .then((res) => res.text())
        .then((text) => {
          setCurrentContent(text);
          setContent(text);
          setHasChanges(false);
          setEditingFromVersion(null);
        })
        .catch((err) => {
          console.error("Error fetching corpus description:", err);
          setCurrentContent("");
          setContent("");
        });
    } else if (data?.corpus) {
      // No mdDescription yet, start with empty
      setCurrentContent("");
      setContent("");
      setHasChanges(false);
      setEditingFromVersion(null);
    }
  }, [data]);

  // Track changes
  useEffect(() => {
    setHasChanges(content !== currentContent);
  }, [content, currentContent]);

  const handleSave = useCallback(async () => {
    if (!hasChanges) return;

    try {
      const result = await updateDescription({
        variables: {
          corpusId,
          newContent: content,
        },
      });

      if (result.data?.updateCorpusDescription.ok) {
        const message = editingFromVersion
          ? `Created version ${result.data.updateCorpusDescription.version} from edits to version ${editingFromVersion}!`
          : `Description updated! Now at version ${result.data.updateCorpusDescription.version}`;

        toast.success(message, {
          icon: <Check size={20} />,
        });

        await refetch();
        setHasChanges(false);
        setEditingFromVersion(null);
        onUpdate?.();
      } else {
        toast.error(
          result.data?.updateCorpusDescription.message ||
            "Failed to update description"
        );
      }
    } catch (error) {
      console.error("Error updating corpus description:", error);
      toast.error("Failed to update corpus description");
    }
  }, [
    corpusId,
    content,
    hasChanges,
    updateDescription,
    refetch,
    onUpdate,
    editingFromVersion,
  ]);

  const handleReapplyVersion = useCallback(
    async (version: CorpusRevision) => {
      if (!version.snapshot) {
        toast.error("This version does not have a snapshot to reapply");
        return;
      }

      try {
        const result = await updateDescription({
          variables: {
            corpusId,
            newContent: version.snapshot,
          },
        });

        if (result.data?.updateCorpusDescription.ok) {
          toast.success(
            `Version ${version.version} reapplied as new version ${result.data.updateCorpusDescription.version}!`,
            { icon: <Check size={20} /> }
          );

          await refetch();
          setViewingVersion(null);
          setSelectedVersion(null);
          onUpdate?.();
        } else {
          toast.error(
            result.data?.updateCorpusDescription.message ||
              "Failed to reapply version"
          );
        }
      } catch (error) {
        console.error("Error reapplying version:", error);
        toast.error("Failed to reapply version");
      }
    },
    [corpusId, updateDescription, refetch, onUpdate]
  );

  const handleEditFromVersion = (version: CorpusRevision) => {
    if (!version.snapshot) {
      toast.error("This version does not have a snapshot to edit from");
      return;
    }

    setContent(version.snapshot);
    setEditingFromVersion(version.version);
    setViewingVersion(null);
    setSelectedVersion(null);
    toast.info(
      `Editing from version ${version.version}. Make your changes and save.`
    );
  };

  const handleVersionClick = (version: CorpusRevision) => {
    if (selectedVersion === version.version) {
      setSelectedVersion(null);
      setViewingVersion(null);
    } else {
      setSelectedVersion(version.version);
      setViewingVersion(version);
    }
  };

  const handleClose = () => {
    if (hasChanges) {
      if (
        window.confirm(
          "You have unsaved changes. Are you sure you want to close?"
        )
      ) {
        onClose();
      }
    } else {
      onClose();
    }
  };

  const revisions = data?.corpus.descriptionRevisions || [];

  // Calculate the actual current version (highest version number)
  const currentVersion =
    revisions.length > 0 ? Math.max(...revisions.map((r) => r.version)) : 0;

  // Sort revisions by version number in descending order for display
  const sortedRevisions = [...revisions].sort((a, b) => b.version - a.version);

  return (
    <StyledModal open={isOpen} onClose={handleClose} closeIcon>
      <ModalHeader>
        <Header
          as="h2"
          style={{
            margin: 0,
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            minWidth: 0,
          }}
        >
          <BookOpen size={20} />
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            Edit Corpus Description
          </span>
          {hasChanges && (
            <EditingIndicator
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", damping: 15 }}
            >
              <Clock size={14} />
              Unsaved changes
            </EditingIndicator>
          )}
          {editingFromVersion && (
            <EditingIndicator
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", damping: 15 }}
              style={{ background: "#ddd6fe", color: "#6b21a8" }}
            >
              <GitBranch size={14} />
              Editing from v{editingFromVersion}
            </EditingIndicator>
          )}
        </Header>
      </ModalHeader>

      <ModalContent>
        <ContentWrapper>
          <EditorContainer>
            <EditorHeader>
              <h3>
                <FileText size={24} />
                {data?.corpus.title || "Corpus"}
              </h3>
              <div className="meta">
                <div className="meta-item">
                  <User size={14} />
                  {data?.corpus.creator.email || "Creator"}
                </div>
                <div className="meta-item">
                  <GitBranch size={14} />
                  Version {currentVersion || 0}
                </div>
                <div className="meta-item">
                  <Clock size={14} />
                  Modified{" "}
                  {data?.corpus.modified
                    ? formatDistanceToNow(new Date(data.corpus.modified), {
                        addSuffix: true,
                      })
                    : "recently"}
                </div>
              </div>
            </EditorHeader>

            <EditorWrapper>
              <Editor
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Write your corpus description in Markdown..."
              />
              <Preview>
                <SafeMarkdown>{content}</SafeMarkdown>
              </Preview>
            </EditorWrapper>
          </EditorContainer>

          <AnimatePresence>
            {showHistory && (
              <>
                <HistoryBackdrop
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  onClick={() => setShowHistory(false)}
                />
                <HistoryPanel
                  initial={{
                    x:
                      typeof window !== "undefined" && window.innerWidth <= 768
                        ? "100%"
                        : 0,
                    width:
                      typeof window !== "undefined" && window.innerWidth <= 768
                        ? "100%"
                        : 0,
                    opacity: 0,
                  }}
                  animate={{
                    x: 0,
                    width:
                      typeof window !== "undefined" && window.innerWidth <= 768
                        ? "100%"
                        : "min(400px, 40vw)",
                    opacity: 1,
                  }}
                  exit={{
                    x:
                      typeof window !== "undefined" && window.innerWidth <= 768
                        ? "100%"
                        : 0,
                    width:
                      typeof window !== "undefined" && window.innerWidth <= 768
                        ? "100%"
                        : 0,
                    opacity: 0,
                  }}
                  transition={{ type: "spring", damping: 25, stiffness: 300 }}
                >
                  <HistoryHeader>
                    <div className="header-content">
                      <div className="header-info">
                        <h4>
                          <History size={18} />
                          Version History
                        </h4>
                        <div className="version-count">
                          {revisions.length} version
                          {revisions.length !== 1 ? "s" : ""}
                        </div>
                      </div>
                      <MobileHistoryCloseButton
                        onClick={() => setShowHistory(false)}
                        aria-label="Close history"
                      >
                        <X size={20} />
                      </MobileHistoryCloseButton>
                    </div>
                  </HistoryHeader>

                  <HistoryList>
                    {sortedRevisions.map(
                      (revision: CorpusRevision, index: number) => (
                        <div key={revision.id}>
                          <VersionItem
                            $isActive={revision.version === currentVersion}
                            $isViewing={
                              revision.version === viewingVersion?.version
                            }
                            onClick={() => handleVersionClick(revision)}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                          >
                            <div className="version-header">
                              <div className="version-number">
                                Version {revision.version}
                                {revision.version === currentVersion && (
                                  <span className="version-badge">Current</span>
                                )}
                                {index === 0 &&
                                  revision.version !== currentVersion && (
                                    <span className="version-badge">
                                      Latest
                                    </span>
                                  )}
                              </div>
                            </div>
                            <div className="version-meta">
                              <div className="meta-row">
                                <User size={12} />
                                {revision.author.email}
                              </div>
                              <div className="meta-row">
                                <Clock size={12} />
                                {format(
                                  new Date(revision.created),
                                  "MMM d, yyyy 'at' h:mm a"
                                )}
                              </div>
                            </div>
                          </VersionItem>

                          <AnimatePresence>
                            {viewingVersion?.version === revision.version && (
                              <VersionDetails
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: "auto" }}
                                exit={{ opacity: 0, height: 0 }}
                                transition={{ duration: 0.2 }}
                              >
                                <div
                                  style={{
                                    fontSize: "0.875rem",
                                    color: "#64748b",
                                    marginBottom: "0.5rem",
                                  }}
                                >
                                  <Eye
                                    size={14}
                                    style={{
                                      display: "inline",
                                      marginRight: "0.25rem",
                                    }}
                                  />
                                  Version {revision.version} snapshot
                                </div>
                                {revision.snapshot ? (
                                  <>
                                    <div className="version-content">
                                      <SafeMarkdown>
                                        {revision.snapshot}
                                      </SafeMarkdown>
                                    </div>
                                    <div className="version-actions">
                                      <StyledButton
                                        $variant="success"
                                        $size="small"
                                        onClick={() =>
                                          handleReapplyVersion(revision)
                                        }
                                        disabled={updating}
                                      >
                                        <Copy size={14} />
                                        Reapply as New Version
                                      </StyledButton>
                                      <StyledButton
                                        $variant="primary"
                                        $size="small"
                                        onClick={() =>
                                          handleEditFromVersion(revision)
                                        }
                                        disabled={updating || hasChanges}
                                      >
                                        <Edit size={14} />
                                        Edit from This Version
                                      </StyledButton>
                                      {hasChanges && (
                                        <div
                                          style={{
                                            fontSize: "0.75rem",
                                            color: "#ef4444",
                                            width: "100%",
                                            marginTop: "0.5rem",
                                          }}
                                        >
                                          Save current changes first
                                        </div>
                                      )}
                                    </div>
                                  </>
                                ) : (
                                  <div
                                    style={{
                                      padding: "1rem",
                                      background: "#fef2f2",
                                      borderRadius: "6px",
                                      color: "#991b1b",
                                      fontSize: "0.875rem",
                                      display: "flex",
                                      alignItems: "center",
                                      gap: "0.5rem",
                                    }}
                                  >
                                    <AlertCircle size={16} />
                                    This version does not have a snapshot
                                    available
                                  </div>
                                )}
                              </VersionDetails>
                            )}
                          </AnimatePresence>
                        </div>
                      )
                    )}
                  </HistoryList>
                </HistoryPanel>
              </>
            )}
          </AnimatePresence>
        </ContentWrapper>
      </ModalContent>

      <ActionBar>
        <ActionGroup>
          <StyledButton
            $variant="secondary"
            onClick={() => setShowHistory(!showHistory)}
          >
            <History size={16} />
            {showHistory ? "Hide" : "Show"} History
          </StyledButton>
        </ActionGroup>

        <ActionGroup>
          {editingFromVersion && (
            <StyledButton
              $variant="secondary"
              onClick={() => {
                if (currentContent !== undefined) {
                  setContent(currentContent);
                  setEditingFromVersion(null);
                }
              }}
            >
              <X size={16} />
              Cancel Version Edit
            </StyledButton>
          )}
          <StyledButton $variant="secondary" onClick={handleClose}>
            <X size={16} />
            Close
          </StyledButton>
          <StyledButton
            $variant="primary"
            onClick={handleSave}
            disabled={!hasChanges || updating}
            loading={updating}
          >
            <Save size={16} />
            Save Changes
            {hasChanges && !updating && (
              <motion.span
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                style={{
                  display: "inline-block",
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#10b981",
                  marginLeft: 8,
                }}
              />
            )}
          </StyledButton>
        </ActionGroup>
      </ActionBar>
    </StyledModal>
  );
};
