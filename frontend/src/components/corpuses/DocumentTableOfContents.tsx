import React, { useMemo, useEffect, useRef } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { useNavigate, useLocation } from "react-router-dom";
import {
  FileText,
  ChevronRight,
  ChevronDown,
  ListTree,
  AlertTriangle,
  AlertCircle,
  File,
  FileSpreadsheet,
  FileImage,
  FileCode,
  ChevronsUpDown,
  ChevronsDownUp,
  Loader2,
} from "lucide-react";

import {
  GET_DOCUMENT_RELATIONSHIPS,
  GetDocumentRelationshipsOutput,
  GetDocumentRelationshipsInput,
  DocumentRelationshipNode,
  GET_CORPUS_DOCUMENTS_FOR_TOC,
  GetCorpusDocumentsForTocInput,
  GetCorpusDocumentsForTocOutput,
} from "../../graphql/queries";
import { openedCorpus, tocExpandAll } from "../../graphql/cache";
import { updateTocExpandedParam } from "../../utils/navigationUtils";
import { navigateToRelationshipDocument } from "../../utils/navigationUtils";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import {
  DOCUMENT_RELATIONSHIP_TOC_LIMIT,
  CORPUS_DOCUMENTS_TOC_LIMIT,
} from "../../assets/configurations/constants";

// ============================================================================
// TYPES
// ============================================================================

interface DocumentTableOfContentsProps {
  corpusId: string;
  maxDepth?: number;
  /** When true, renders without outer container (for embedding in tabs) */
  embedded?: boolean;
}

interface DocumentNode {
  id: string;
  title: string;
  description?: string;
  fileType?: string;
  slug?: string;
  icon?: string;
  children: DocumentNode[];
}

// ============================================================================
// STYLED COMPONENTS
// ============================================================================

const Container = styled.div<{ $embedded?: boolean }>`
  padding: ${(props) => (props.$embedded ? "20px 24px" : "16px")};
  background: ${OS_LEGAL_COLORS.surface};
  border: ${(props) =>
    props.$embedded ? "none" : `1px solid ${OS_LEGAL_COLORS.border}`};
  border-radius: ${(props) =>
    props.$embedded ? "0" : OS_LEGAL_SPACING.borderRadiusCard};
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const HeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const ExpandToggleButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  background: ${OS_LEGAL_COLORS.surface};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.accent};
    color: ${OS_LEGAL_COLORS.accent};
  }

  &:focus {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: 2px;
  }
`;

const Title = styled.h3`
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: flex;
  align-items: center;
  gap: 8px;
`;

const TreeContainer = styled.div`
  /* Empty state text */
  .empty-state {
    text-align: center;
    padding: 48px 24px;
    color: ${OS_LEGAL_COLORS.textMuted};

    .empty-icon {
      margin-bottom: 16px;
      color: ${OS_LEGAL_COLORS.border};
    }

    .empty-title {
      font-size: 1.125rem;
      font-weight: 600;
      color: ${OS_LEGAL_COLORS.textSecondary};
      margin-bottom: 8px;
    }

    .empty-description {
      font-size: 0.875rem;
      max-width: 400px;
      margin: 0 auto;
      line-height: 1.5;
    }
  }
`;

const TreeNode = styled.div<{ $depth: number }>`
  margin-left: ${(props) => props.$depth * 24}px;
`;

const NodeItem = styled.div<{ $hasChildren: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 18px;
  margin: 6px 0;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.border};
  }

  &:focus {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: -2px;
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: -2px;
  }
`;

const ChevronContainer = styled.span<{ $visible: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: ${OS_LEGAL_COLORS.textMuted};
  opacity: ${(props) => (props.$visible ? 1 : 0)};
  cursor: ${(props) => (props.$visible ? "pointer" : "default")};
  border-radius: 4px;
  margin-top: 2px;

  &:hover {
    background: ${(props) =>
      props.$visible ? OS_LEGAL_COLORS.border : "transparent"};
  }
`;

const IconContainer = styled.div<{ $fileType?: string }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.accentLight};
  color: ${OS_LEGAL_COLORS.accent};
`;

const NodeContent = styled.div`
  flex: 1;
  min-width: 0;
`;

const NodeTitle = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.0625rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.35;
  margin-bottom: 6px;

  /* Allow wrapping but limit to 2 lines */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const NodeDescription = styled.div`
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.5;
  max-height: calc(1.5em * 2); /* Exactly 2 lines */

  /* Limit to 2 lines with ellipsis */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const NodeMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
`;

const FileTypeBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textMuted};
  text-transform: uppercase;
  letter-spacing: 0.03em;
`;

const LoadingState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  color: ${OS_LEGAL_COLORS.textMuted};
  gap: 12px;
`;

const ErrorState = styled.div`
  text-align: center;
  padding: 48px 24px;
  color: ${OS_LEGAL_COLORS.danger};

  .error-icon {
    margin-bottom: 12px;
  }
`;

const WarningBanner = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: #fef3c7;
  border: 1px solid #f59e0b;
  border-radius: 8px;
  color: #92400e;
  font-size: 0.875rem;

  .warning-icon {
    flex-shrink: 0;
    margin-top: 2px;
  }

  .warning-text {
    flex: 1;
    line-height: 1.4;
  }
`;

// ============================================================================
// HELPERS
// ============================================================================

/** Get icon component based on file type */
const getFileIcon = (fileType?: string) => {
  if (!fileType) return FileText;

  const type = fileType.toLowerCase();
  if (type.includes("pdf")) return FileText;
  if (type.includes("spreadsheet") || type.includes("excel") || type === "xlsx")
    return FileSpreadsheet;
  if (type.includes("image") || ["png", "jpg", "jpeg", "gif"].includes(type))
    return FileImage;
  if (
    type.includes("code") ||
    ["json", "xml", "html", "css", "js"].includes(type)
  )
    return FileCode;
  return File;
};

/** Format file type for display */
const formatFileType = (fileType?: string): string => {
  if (!fileType) return "Document";

  const type = fileType.toLowerCase();
  if (type.includes("pdf") || type === "application/pdf") return "PDF";
  if (type.includes("word") || type === "docx") return "Word";
  if (type.includes("excel") || type === "xlsx") return "Excel";
  if (type.includes("text") || type === "txt") return "Text";
  if (type.includes("image")) return "Image";

  // Return the type without extension or mime prefix
  return type
    .replace(/^application\//, "")
    .toUpperCase()
    .slice(0, 8);
};

// ============================================================================
// COMPONENT
// ============================================================================

export const DocumentTableOfContents: React.FC<
  DocumentTableOfContentsProps
> = ({ corpusId, maxDepth = 4, embedded = false }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [expandedNodes, setExpandedNodes] = React.useState<Set<string>>(
    new Set()
  );

  // URL-driven expand all state
  const expandAllFromUrl = useReactiveVar(tocExpandAll);

  // Query for document relationships in this corpus
  const {
    data: relationshipsData,
    loading: relationshipsLoading,
    error: relationshipsError,
  } = useQuery<GetDocumentRelationshipsOutput, GetDocumentRelationshipsInput>(
    GET_DOCUMENT_RELATIONSHIPS,
    {
      variables: {
        corpusId,
        first: DOCUMENT_RELATIONSHIP_TOC_LIMIT,
      },
      skip: !corpusId,
      fetchPolicy: "cache-and-network",
    }
  );

  // Query for all documents in this corpus (to include standalone docs)
  const {
    data: documentsData,
    loading: documentsLoading,
    error: documentsError,
  } = useQuery<GetCorpusDocumentsForTocOutput, GetCorpusDocumentsForTocInput>(
    GET_CORPUS_DOCUMENTS_FOR_TOC,
    {
      variables: {
        corpusId,
        first: CORPUS_DOCUMENTS_TOC_LIMIT,
      },
      skip: !corpusId,
      fetchPolicy: "cache-and-network",
    }
  );

  // Combined loading and error states
  const loading = relationshipsLoading || documentsLoading;
  const error = relationshipsError || documentsError;

  // Check if we've hit the limits (potential truncation)
  const relationshipTotalCount =
    relationshipsData?.documentRelationships?.totalCount ?? 0;
  const documentsTotalCount = documentsData?.documents?.totalCount ?? 0;
  const isLimitExceeded =
    relationshipTotalCount > DOCUMENT_RELATIONSHIP_TOC_LIMIT ||
    documentsTotalCount > CORPUS_DOCUMENTS_TOC_LIMIT;

  // Build tree from relationships AND all corpus documents
  const { rootNodes, hasCircularRefs, circularRefDocs, allNodeIds } =
    useMemo(() => {
      const relationships =
        relationshipsData?.documentRelationships?.edges || [];
      const allDocuments = documentsData?.documents?.edges || [];

      // If we don't have documents data yet, return empty (still loading)
      if (allDocuments.length === 0 && documentsLoading) {
        return {
          rootNodes: [],
          hasCircularRefs: false,
          circularRefDocs: [],
          allNodeIds: [],
        };
      }

      // Filter to only "parent" labeled relationships
      const parentRelationships = relationships
        .map((e) => e.node)
        .filter(
          (rel): rel is DocumentRelationshipNode =>
            rel != null &&
            rel.relationshipType === "RELATIONSHIP" &&
            rel.annotationLabel?.text?.toLowerCase() === "parent"
        );

      // Build a map of document info from ALL corpus documents
      const documentMap = new Map<
        string,
        {
          id: string;
          title: string;
          description?: string;
          fileType?: string;
          slug?: string;
          icon?: string;
        }
      >();

      // First, add all documents from the corpus (standalone and related)
      allDocuments.forEach((edge) => {
        const doc = edge.node;
        documentMap.set(doc.id, {
          id: doc.id,
          title: doc.title || "Untitled",
          description: undefined, // Not available in lightweight query
          fileType: doc.fileType || undefined,
          slug: doc.slug,
          icon: doc.icon || undefined,
        });
      });

      // Build parent-children map from relationships
      // In "parent" relationships: source has parent target (i.e., target is parent of source)
      // So: source.parent = target
      const parentMap = new Map<string, string>(); // child -> parent
      const childrenMap = new Map<string, string[]>(); // parent -> children

      parentRelationships.forEach((rel) => {
        const sourceId = rel.sourceDocument.id;
        const targetId = rel.targetDocument.id;

        // Update document info with richer data from relationships if available
        if (rel.sourceDocument.title) {
          documentMap.set(sourceId, {
            ...documentMap.get(sourceId),
            id: sourceId,
            title: rel.sourceDocument.title || "Untitled",
            description: rel.sourceDocument.description || undefined,
            fileType: rel.sourceDocument.fileType || undefined,
            slug: rel.sourceDocument.slug,
            icon: rel.sourceDocument.icon,
          });
        }
        if (rel.targetDocument.title) {
          documentMap.set(targetId, {
            ...documentMap.get(targetId),
            id: targetId,
            title: rel.targetDocument.title || "Untitled",
            description: rel.targetDocument.description || undefined,
            fileType: rel.targetDocument.fileType || undefined,
            slug: rel.targetDocument.slug,
            icon: rel.targetDocument.icon,
          });
        }

        // Source's parent is target (source "has parent" target)
        parentMap.set(sourceId, targetId);

        // Target has source as a child
        const existing = childrenMap.get(targetId) || [];
        childrenMap.set(targetId, [...existing, sourceId]);
      });

      // Find root documents: ANY document that has no parent
      // This includes both docs with children AND standalone docs
      const allDocIds = new Set([...documentMap.keys()]);
      const rootDocIds = Array.from(allDocIds).filter(
        (id) => !parentMap.has(id)
      );

      // Track circular references for user warning
      const circularRefs: string[] = [];

      // Build tree recursively with depth limit and cycle detection
      const buildTree = (
        docId: string,
        currentDepth: number,
        visited: Set<string> = new Set()
      ): DocumentNode | null => {
        // Prevent infinite recursion from circular references
        if (visited.has(docId)) {
          const docTitle = documentMap.get(docId)?.title || docId;
          circularRefs.push(docTitle);
          return null;
        }
        if (currentDepth > maxDepth) return null;

        const docInfo = documentMap.get(docId);
        if (!docInfo) return null;

        // Add current node to visited set for this branch
        const branchVisited = new Set(visited).add(docId);

        const childIds = childrenMap.get(docId) || [];
        // Sort children alphabetically by title
        const sortedChildIds = [...childIds].sort((a, b) => {
          const titleA = documentMap.get(a)?.title || "";
          const titleB = documentMap.get(b)?.title || "";
          return titleA.localeCompare(titleB);
        });

        const children = sortedChildIds
          .map((childId) => buildTree(childId, currentDepth + 1, branchVisited))
          .filter((child): child is DocumentNode => child !== null);

        return {
          id: docInfo.id,
          title: docInfo.title,
          description: docInfo.description,
          fileType: docInfo.fileType,
          slug: docInfo.slug,
          icon: docInfo.icon,
          children,
        };
      };

      // Build trees from root nodes, sorted alphabetically
      const roots = rootDocIds
        .map((id) => buildTree(id, 0, new Set()))
        .filter((node): node is DocumentNode => node !== null)
        .sort((a, b) => a.title.localeCompare(b.title));

      // Collect all node IDs that have children (for expand all)
      const collectExpandableIds = (nodes: DocumentNode[]): string[] => {
        const ids: string[] = [];
        for (const node of nodes) {
          if (node.children.length > 0) {
            ids.push(node.id);
            ids.push(...collectExpandableIds(node.children));
          }
        }
        return ids;
      };

      return {
        rootNodes: roots,
        hasCircularRefs: circularRefs.length > 0,
        circularRefDocs: circularRefs,
        allNodeIds: collectExpandableIds(roots),
      };
    }, [relationshipsData, documentsData, documentsLoading, maxDepth]);

  // Track if we've successfully handled the initial expand all state
  // (only true once we've actually expanded nodes, not just attempted to)
  const hasHandledInitialExpandRef = useRef<boolean>(false);
  // Track the last value we acted upon to detect actual user-driven changes
  const lastExpandAllValueRef = useRef<boolean | null>(null);

  // Sync expand state from URL parameter
  // Handles both initial load with tocExpanded=true and subsequent user-driven toggles
  useEffect(() => {
    // On initial mount with expandAllFromUrl=true, wait for nodes then expand
    if (!hasHandledInitialExpandRef.current && expandAllFromUrl) {
      if (allNodeIds.length > 0) {
        // Now we have nodes - expand them and mark as handled
        setExpandedNodes(new Set(allNodeIds));
        hasHandledInitialExpandRef.current = true;
        lastExpandAllValueRef.current = expandAllFromUrl;
      }
      // If no nodes yet, don't mark as handled - wait for data to load
      return;
    }

    // Mark as handled if expandAllFromUrl is false on initial mount
    if (!hasHandledInitialExpandRef.current && !expandAllFromUrl) {
      hasHandledInitialExpandRef.current = true;
      lastExpandAllValueRef.current = expandAllFromUrl;
      return;
    }

    // After initial handling, respond to explicit user-driven changes
    if (lastExpandAllValueRef.current === expandAllFromUrl) {
      // Value hasn't changed - nothing to do
      return;
    }

    const wasExpanded = lastExpandAllValueRef.current;
    lastExpandAllValueRef.current = expandAllFromUrl;

    if (expandAllFromUrl && !wasExpanded && allNodeIds.length > 0) {
      // User toggled expand all ON
      setExpandedNodes(new Set(allNodeIds));
    } else if (!expandAllFromUrl && wasExpanded) {
      // User toggled expand all OFF
      setExpandedNodes(new Set());
    }
  }, [expandAllFromUrl, allNodeIds]);

  // Check if all expandable nodes are currently expanded
  const allExpanded = useMemo(() => {
    if (allNodeIds.length === 0) return false;
    return allNodeIds.every((id) => expandedNodes.has(id));
  }, [allNodeIds, expandedNodes]);

  // Toggle expand/collapse all via URL
  const handleToggleExpandAll = () => {
    if (allExpanded) {
      // Collapse all - update URL
      updateTocExpandedParam(location, navigate, false);
      setExpandedNodes(new Set());
    } else {
      // Expand all - update URL
      updateTocExpandedParam(location, navigate, true);
      setExpandedNodes(new Set(allNodeIds));
    }
  };

  // Handle document click - uses shared utility for type safety
  const handleDocumentClick = (doc: {
    id: string;
    title: string;
    slug?: string;
  }) => {
    const corpus = openedCorpus();
    navigateToRelationshipDocument(
      doc,
      corpus,
      navigate,
      window.location.pathname
    );
  };

  // Toggle expand/collapse
  const toggleNode = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  // Handle keyboard navigation for accessibility
  const handleKeyDown = (
    e: React.KeyboardEvent,
    node: DocumentNode,
    hasChildren: boolean,
    isExpanded: boolean
  ) => {
    switch (e.key) {
      case "Enter":
      case " ":
        e.preventDefault();
        handleDocumentClick(node);
        break;
      case "ArrowRight":
        e.preventDefault();
        if (hasChildren && !isExpanded) {
          setExpandedNodes((prev) => new Set(prev).add(node.id));
        }
        break;
      case "ArrowLeft":
        e.preventDefault();
        if (hasChildren && isExpanded) {
          setExpandedNodes((prev) => {
            const next = new Set(prev);
            next.delete(node.id);
            return next;
          });
        }
        break;
    }
  };

  // Render a tree node recursively
  const renderNode = (node: DocumentNode, depth: number) => {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children.length > 0;
    const FileIcon = getFileIcon(node.fileType);

    return (
      <TreeNode key={node.id} $depth={depth}>
        <NodeItem
          $hasChildren={hasChildren}
          onClick={() => handleDocumentClick(node)}
          onKeyDown={(e) => handleKeyDown(e, node, hasChildren, isExpanded)}
          role="treeitem"
          tabIndex={0}
          aria-expanded={hasChildren ? isExpanded : undefined}
          aria-label={`${node.title}${
            hasChildren ? `, ${isExpanded ? "expanded" : "collapsed"}` : ""
          }`}
        >
          <ChevronContainer
            className="chevron"
            $visible={hasChildren}
            onClick={(e) => hasChildren && toggleNode(node.id, e)}
            aria-hidden="true"
          >
            {hasChildren &&
              (isExpanded ? (
                <ChevronDown size={16} />
              ) : (
                <ChevronRight size={16} />
              ))}
          </ChevronContainer>

          <IconContainer $fileType={node.fileType}>
            <FileIcon size={22} />
          </IconContainer>

          <NodeContent>
            <NodeTitle title={node.title}>{node.title}</NodeTitle>
            {node.description && (
              <NodeDescription title={node.description}>
                {node.description}
              </NodeDescription>
            )}
            <NodeMeta>
              <FileTypeBadge>{formatFileType(node.fileType)}</FileTypeBadge>
            </NodeMeta>
          </NodeContent>
        </NodeItem>
        {hasChildren && isExpanded && (
          <div role="group">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </TreeNode>
    );
  };

  // Wrapper component that conditionally renders container
  const Wrapper: React.FC<{
    children: React.ReactNode;
    showExpandToggle?: boolean;
  }> = ({ children, showExpandToggle = false }) =>
    embedded ? (
      <Container $embedded>{children}</Container>
    ) : (
      <Container>
        <Header>
          <HeaderLeft>
            <Title>
              <ListTree size={18} />
              Table of Contents
            </Title>
          </HeaderLeft>
          {showExpandToggle && allNodeIds.length > 0 && (
            <ExpandToggleButton
              onClick={handleToggleExpandAll}
              aria-label={allExpanded ? "Collapse all" : "Expand all"}
            >
              {allExpanded ? (
                <>
                  <ChevronsDownUp size={14} />
                  Collapse All
                </>
              ) : (
                <>
                  <ChevronsUpDown size={14} />
                  Expand All
                </>
              )}
            </ExpandToggleButton>
          )}
        </Header>
        {children}
      </Container>
    );

  if (loading) {
    return (
      <Wrapper>
        <LoadingState>
          <Loader2 size={32} className="animate-spin" />
          <span>Loading document structure...</span>
        </LoadingState>
      </Wrapper>
    );
  }

  if (error) {
    return (
      <Wrapper>
        <ErrorState>
          <AlertCircle size={32} className="error-icon" />
          <div>Failed to load document structure</div>
        </ErrorState>
      </Wrapper>
    );
  }

  if (rootNodes.length === 0) {
    // Show empty state when there are no documents in the corpus
    return (
      <Wrapper>
        <TreeContainer>
          <div className="empty-state">
            <ListTree size={48} className="empty-icon" />
            <div className="empty-title">No Documents</div>
            <div className="empty-description">
              This corpus doesn't have any documents yet. Add documents to see
              them in the table of contents.
            </div>
          </div>
        </TreeContainer>
      </Wrapper>
    );
  }

  return (
    <Wrapper showExpandToggle>
      {isLimitExceeded && (
        <WarningBanner role="alert">
          <AlertTriangle size={18} className="warning-icon" />
          <span className="warning-text">
            This corpus has many documents. Some may not appear in the table of
            contents due to display limits.
          </span>
        </WarningBanner>
      )}
      {hasCircularRefs && (
        <WarningBanner role="alert">
          <AlertTriangle size={18} className="warning-icon" />
          <span className="warning-text">
            Circular parent references detected. Some documents may not appear
            in the hierarchy. Check the parent relationships for:{" "}
            {circularRefDocs.slice(0, 3).join(", ")}
            {circularRefDocs.length > 3 &&
              ` and ${circularRefDocs.length - 3} more`}
          </span>
        </WarningBanner>
      )}
      <TreeContainer role="tree" aria-label="Document hierarchy">
        {rootNodes.map((node) => renderNode(node, 0))}
      </TreeContainer>
    </Wrapper>
  );
};

export default DocumentTableOfContents;
