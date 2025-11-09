import React, { useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Icon, Loader } from "semantic-ui-react";
import styled from "styled-components";
import { CorpusType, DocumentType } from "../../types/graphql-api";
import { getCorpusUrl, getDocumentUrl } from "../../utils/navigationUtils";

const TreeContainer = styled.div`
  padding: 1rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  user-select: none;
`;

const TreeNode = styled.div`
  margin-left: ${(props: { level: number }) => props.level * 20}px;
  margin-bottom: 4px;
`;

const NodeContent = styled.div<{ isSelected?: boolean; isFolder?: boolean }>`
  display: flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  background: ${(props) => (props.isSelected ? "#e3f2fd" : "transparent")};
  transition: background 0.15s ease;

  &:hover {
    background: ${(props) => (props.isSelected ? "#bbdefb" : "#f5f5f5")};
  }

  .node-icon {
    margin-right: 8px;
    transition: transform 0.2s ease;
  }

  .folder-chevron {
    margin-right: 4px;
    font-size: 0.9em;
    transition: transform 0.2s ease;
  }

  .node-label {
    flex: 1;
    font-size: 14px;
    color: #333;
    font-weight: ${(props) => (props.isFolder ? "500" : "normal")};
  }

  .node-count {
    font-size: 12px;
    color: #666;
    margin-left: 8px;
  }
`;

const ExpandIcon = styled(Icon)<{ expanded: boolean }>`
  transform: rotate(${(props) => (props.expanded ? "90deg" : "0deg")});
`;

interface TreeNodeData {
  id: string;
  type: "folder" | "document";
  name: string;
  icon?: string | null;
  slug?: string;
  creator?: { slug?: string };
  children?: TreeNodeData[];
  documentCount?: number;
  permissions?: string[];
}

interface FolderTreeNodeProps {
  node: TreeNodeData;
  level: number;
  selectedId?: string;
  onSelect: (node: TreeNodeData) => void;
  canEdit?: boolean;
}

const FolderTreeNode: React.FC<FolderTreeNodeProps> = ({
  node,
  level,
  selectedId,
  onSelect,
  canEdit,
}) => {
  const [expanded, setExpanded] = useState(level === 0);
  const isFolder = node.type === "folder";
  const hasChildren = isFolder && node.children && node.children.length > 0;
  const isSelected = selectedId === node.id;

  const handleToggle = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (hasChildren) {
        setExpanded(!expanded);
      }
    },
    [hasChildren, expanded]
  );

  const handleSelect = useCallback(() => {
    onSelect(node);
  }, [node, onSelect]);

  return (
    <>
      <TreeNode level={level}>
        <NodeContent
          isSelected={isSelected}
          isFolder={isFolder}
          onClick={handleSelect}
        >
          {isFolder && hasChildren && (
            <ExpandIcon
              name="chevron right"
              className="folder-chevron"
              expanded={expanded}
              onClick={handleToggle}
            />
          )}
          {isFolder && !hasChildren && (
            <span className="folder-chevron" style={{ width: "13px" }} />
          )}
          <Icon
            name={
              isFolder
                ? expanded
                  ? "folder open outline"
                  : "folder outline"
                : node.icon || "file outline"
            }
            className="node-icon"
          />
          <span className="node-label">{node.name}</span>
          {isFolder && node.documentCount !== undefined && (
            <span className="node-count">
              {node.documentCount}{" "}
              {node.documentCount === 1 ? "document" : "documents"}
            </span>
          )}
        </NodeContent>
      </TreeNode>
      {expanded && hasChildren && (
        <>
          {node.children!.map((child) => (
            <FolderTreeNode
              key={child.id}
              node={child}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              canEdit={canEdit}
            />
          ))}
        </>
      )}
    </>
  );
};

interface FolderTreeViewProps {
  corpus: CorpusType;
  documents?: DocumentType[];
  loading?: boolean;
  onCorpusSelect?: (corpus: CorpusType) => void;
  onDocumentSelect?: (document: DocumentType) => void;
}

export const FolderTreeView: React.FC<FolderTreeViewProps> = ({
  corpus,
  documents = [],
  loading = false,
  onCorpusSelect,
  onDocumentSelect,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [selectedId, setSelectedId] = useState<string | undefined>(corpus.id);

  // Convert corpus tree to tree node structure
  const buildTreeFromCorpus = useCallback(
    (corpusNode: CorpusType): TreeNodeData => {
      const children: TreeNodeData[] = [];

      // Add sub-corpuses (folders)
      if (corpusNode.children?.edges) {
        corpusNode.children.edges.forEach((edge) => {
          if (edge?.node) {
            children.push(buildTreeFromCorpus(edge.node as CorpusType));
          }
        });
      }

      // Add documents if this is the selected corpus
      if (corpusNode.id === corpus.id && documents.length > 0) {
        documents.forEach((doc) => {
          children.push({
            id: doc.id,
            type: "document",
            name: doc.title || "Untitled Document",
            icon: doc.icon,
            slug: doc.slug,
            creator: doc.creator,
            permissions: doc.myPermissions,
          });
        });
      }

      return {
        id: corpusNode.id,
        type: "folder",
        name: corpusNode.title,
        icon: corpusNode.icon,
        slug: corpusNode.slug,
        creator: corpusNode.creator,
        children,
        documentCount: corpusNode.documents?.totalCount || 0,
        permissions: corpusNode.myPermissions,
      };
    },
    [corpus.id, documents]
  );

  const treeData = buildTreeFromCorpus(corpus);

  const handleNodeSelect = useCallback(
    (node: TreeNodeData) => {
      setSelectedId(node.id);

      if (node.type === "folder") {
        // Navigate to corpus
        const url = getCorpusUrl({
          id: node.id,
          slug: node.slug || "",
          creator: { slug: node.creator?.slug || "" },
        } as any);
        if (url !== "#") {
          navigate(url);
        }
        if (onCorpusSelect) {
          onCorpusSelect({ id: node.id } as CorpusType);
        }
      } else if (node.type === "document") {
        // Navigate to document
        const url = getDocumentUrl(
          {
            id: node.id,
            slug: node.slug || "",
            creator: { slug: node.creator?.slug || "" },
          } as any,
          corpus as any
        );
        if (url !== "#") {
          navigate(url);
        }
        if (onDocumentSelect) {
          onDocumentSelect({ id: node.id } as DocumentType);
        }
      }
    },
    [corpus, navigate, onCorpusSelect, onDocumentSelect]
  );

  if (loading) {
    return (
      <TreeContainer>
        <Loader active inline="centered">
          Loading folder tree...
        </Loader>
      </TreeContainer>
    );
  }

  return (
    <TreeContainer>
      <FolderTreeNode
        node={treeData}
        level={0}
        selectedId={selectedId}
        onSelect={handleNodeSelect}
        canEdit={corpus.myPermissions?.includes("update_corpus")}
      />
    </TreeContainer>
  );
};
