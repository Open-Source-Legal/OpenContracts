import React, { useMemo, useEffect, useRef, useState } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { Spinner } from "@os-legal/ui";
import { useNavigate } from "react-router-dom";
import {
  ChevronRight,
  ChevronDown,
  BookOpen,
  AlertTriangle,
  Hash,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

import {
  GET_DOCUMENT_ANNOTATION_INDEX,
  GetDocumentAnnotationIndexOutput,
  GetDocumentAnnotationIndexInput,
  AnnotationIndexNode,
} from "../../graphql/queries";
import { openedCorpus, tocExpandAll } from "../../graphql/cache";
import { navigateToRelationshipDocument } from "../../utils/navigationUtils";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
} from "../../assets/configurations/osLegalStyles";
import { mediaQuery } from "./styles/corpusDesignTokens";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../../assets/configurations/constants";

// ============================================================================
// TYPES
// ============================================================================

interface DocumentAnnotationIndexProps {
  /** Document ID (global relay ID) to fetch annotation index for */
  documentId: string;
  /** Optional corpus ID for scoping */
  corpusId?: string;
  /** Maximum tree depth */
  maxDepth?: number;
  /** When true, renders without outer container (for embedding in tabs) */
  embedded?: boolean;
  /** Case-insensitive filter applied to section titles and descriptions */
  filterQuery?: string;
}

interface SectionNode {
  id: string;
  title: string;
  longDescription?: string;
  page: number;
  children: SectionNode[];
}

// ============================================================================
// STYLED COMPONENTS
// ============================================================================

const Container = styled.div<{ $embedded?: boolean }>`
  padding: ${(props) => (props.$embedded ? "0" : "16px")};
  background: transparent;
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
  margin-left: ${(props) => props.$depth * 16}px;
  ${(props) =>
    props.$depth > 0 &&
    `
    border-left: 1px solid ${OS_LEGAL_COLORS.border};
    margin-left: ${props.$depth * 16 - 1}px;
    padding-left: 1px;
  `}

  ${mediaQuery.tablet} {
    margin-left: ${(props) => props.$depth * 12}px;
    ${(props) =>
      props.$depth > 0 &&
      `
      margin-left: ${props.$depth * 12 - 1}px;
    `}
  }
`;

const NodeItem = styled.div<{ $hasDescription: boolean }>`
  display: flex;
  align-items: ${(props) => (props.$hasDescription ? "flex-start" : "center")};
  gap: 12px;
  padding: ${(props) => (props.$hasDescription ? "12px 14px" : "10px 14px")};
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }

  &:focus {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: -2px;
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: -2px;
  }

  ${mediaQuery.tablet} {
    gap: 8px;
    padding: ${(props) => (props.$hasDescription ? "10px 12px" : "8px 12px")};
  }
`;

const ChevronContainer = styled.span<{ $visible: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: ${OS_LEGAL_COLORS.textMuted};
  opacity: ${(props) => (props.$visible ? 1 : 0)};
  cursor: ${(props) => (props.$visible ? "pointer" : "default")};
  border-radius: 3px;

  &:hover {
    background: ${(props) =>
      props.$visible ? OS_LEGAL_COLORS.border : "transparent"};
    color: ${(props) =>
      props.$visible ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textMuted};
  }
`;

const IconContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  color: ${OS_LEGAL_COLORS.textSecondary};

  ${mediaQuery.tablet} {
    width: 18px;
    height: 18px;

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

const NodeContent = styled.div`
  flex: 1;
  min-width: 0;
`;

const NodeTitle = styled.div`
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 1.1875rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  ${NodeItem}:hover & {
    color: ${OS_LEGAL_COLORS.accent};
  }

  ${mediaQuery.tablet} {
    font-size: 0.9375rem;
    line-height: 1.4;
  }
`;

const NodeDescription = styled.div`
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.55;
  margin-top: 4px;

  /* Collapsed: 2-line clamp */
  &.collapsed {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* Expanded: full markdown rendering */
  &.expanded {
    p {
      margin: 0.4em 0;
    }
    ul,
    ol {
      margin: 0.4em 0;
      padding-left: 1.5em;
    }
  }

  ${mediaQuery.tablet} {
    font-size: 0.8125rem;
    line-height: 1.4;
    margin-top: 2px;
  }
`;

const PageBadge = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 4px;
  padding: 1px 6px;
  flex-shrink: 0;
  white-space: nowrap;
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
  background: ${OS_LEGAL_COLORS.warningSurface};
  border: 1px solid ${OS_LEGAL_COLORS.warningBorder};
  border-radius: 8px;
  color: ${OS_LEGAL_COLORS.warningText};
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
// COMPONENT
// ============================================================================

export const DocumentAnnotationIndex: React.FC<
  DocumentAnnotationIndexProps
> = ({ documentId, corpusId, maxDepth = 6, embedded = false, filterQuery }) => {
  const navigate = useNavigate();
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(
    new Set()
  );

  // URL-driven expand all state (shared with document TOC)
  const expandAllFromUrl = useReactiveVar(tocExpandAll);

  // Query for annotations with the OC_SECTION label
  const {
    data: annotationsData,
    loading,
    error,
  } = useQuery<
    GetDocumentAnnotationIndexOutput,
    GetDocumentAnnotationIndexInput
  >(GET_DOCUMENT_ANNOTATION_INDEX, {
    variables: {
      documentId,
      corpusId,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    },
    skip: !documentId,
    fetchPolicy: "cache-and-network",
  });

  const isLimitExceeded =
    (annotationsData?.annotations?.totalCount ?? 0) >
    DOCUMENT_ANNOTATION_INDEX_LIMIT;

  // Build tree from flat annotation list using parent FK
  const { rootNodes, hasCircularRefs, allNodeIds } = useMemo(() => {
    const edges = annotationsData?.annotations?.edges || [];
    if (edges.length === 0) {
      return { rootNodes: [], hasCircularRefs: false, allNodeIds: [] };
    }

    // Build lookup map
    const nodeMap = new Map<string, AnnotationIndexNode>();
    edges.forEach((e) => nodeMap.set(e.node.id, e.node));

    // Build parent-child maps
    const childrenMap = new Map<string, string[]>();
    const hasParent = new Set<string>();

    edges.forEach((e) => {
      const node = e.node;
      if (node.parent?.id) {
        hasParent.add(node.id);
        const existing = childrenMap.get(node.parent.id) || [];
        childrenMap.set(node.parent.id, [...existing, node.id]);
      }
    });

    // Root nodes: annotations without a parent (or whose parent isn't in the set)
    const rootIds = edges
      .map((e) => e.node.id)
      .filter((id) => !hasParent.has(id));

    const circularRefs: string[] = [];

    const buildTree = (
      nodeId: string,
      currentDepth: number,
      visited: Set<string> = new Set()
    ): SectionNode | null => {
      if (visited.has(nodeId)) {
        circularRefs.push(nodeId);
        return null;
      }
      if (currentDepth > maxDepth) return null;

      const annot = nodeMap.get(nodeId);
      if (!annot) return null;

      const branchVisited = new Set(visited).add(nodeId);
      const childIds = childrenMap.get(nodeId) || [];
      // Sort children by page number, then by title
      const sortedChildIds = [...childIds].sort((a, b) => {
        const annotA = nodeMap.get(a);
        const annotB = nodeMap.get(b);
        const pageDiff = (annotA?.page ?? 0) - (annotB?.page ?? 0);
        if (pageDiff !== 0) return pageDiff;
        return (annotA?.rawText ?? "").localeCompare(annotB?.rawText ?? "");
      });

      const children = sortedChildIds
        .map((childId) => buildTree(childId, currentDepth + 1, branchVisited))
        .filter((child): child is SectionNode => child !== null);

      return {
        id: annot.id,
        title: annot.rawText || "Untitled Section",
        longDescription: annot.longDescription || undefined,
        page: annot.page,
        children,
      };
    };

    // Build trees from root nodes, sorted by page number
    const roots = rootIds
      .map((id) => buildTree(id, 0, new Set()))
      .filter((node): node is SectionNode => node !== null)
      .sort((a, b) => a.page - b.page);

    // Collect expandable IDs
    const collectExpandableIds = (nodes: SectionNode[]): string[] => {
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
      allNodeIds: collectExpandableIds(roots),
    };
  }, [annotationsData, maxDepth]);

  // Apply filter
  const filteredNodes = useMemo(() => {
    const query = filterQuery?.trim().toLowerCase();
    if (!query) return rootNodes;

    const filterTree = (nodes: SectionNode[]): SectionNode[] => {
      const result: SectionNode[] = [];
      for (const node of nodes) {
        const titleMatch = node.title.toLowerCase().includes(query);
        const descMatch = node.longDescription?.toLowerCase().includes(query);

        if (titleMatch || descMatch) {
          result.push(node);
        } else {
          const filteredChildren = filterTree(node.children);
          if (filteredChildren.length > 0) {
            result.push({ ...node, children: filteredChildren });
          }
        }
      }
      return result;
    };

    return filterTree(rootNodes);
  }, [rootNodes, filterQuery]);

  // Sync expand state from URL parameter
  const hasHandledInitialExpandRef = useRef<boolean>(false);
  const lastExpandAllValueRef = useRef<boolean | null>(null);

  useEffect(() => {
    if (!hasHandledInitialExpandRef.current && expandAllFromUrl) {
      if (allNodeIds.length > 0) {
        setExpandedNodes(new Set(allNodeIds));
        hasHandledInitialExpandRef.current = true;
        lastExpandAllValueRef.current = expandAllFromUrl;
      }
      return;
    }

    if (!hasHandledInitialExpandRef.current && !expandAllFromUrl) {
      hasHandledInitialExpandRef.current = true;
      lastExpandAllValueRef.current = expandAllFromUrl;
      return;
    }

    if (lastExpandAllValueRef.current === expandAllFromUrl) return;

    const wasExpanded = lastExpandAllValueRef.current;
    lastExpandAllValueRef.current = expandAllFromUrl;

    if (expandAllFromUrl && !wasExpanded && allNodeIds.length > 0) {
      setExpandedNodes(new Set(allNodeIds));
    } else if (!expandAllFromUrl && wasExpanded) {
      setExpandedNodes(new Set());
    }
  }, [expandAllFromUrl, allNodeIds]);

  // Auto-expand all nodes when a filter is active so matches are visible
  useEffect(() => {
    if (filterQuery?.trim() && allNodeIds.length > 0) {
      setExpandedNodes(new Set(allNodeIds));
    }
  }, [filterQuery, allNodeIds]);

  // Handle section click - navigate to the document at that page
  const handleSectionClick = (node: SectionNode) => {
    const corpus = openedCorpus();
    // Navigate to the document - the annotation page context will help
    // the viewer scroll to the right location
    navigateToRelationshipDocument(
      { id: documentId, title: node.title, slug: undefined },
      corpus,
      navigate,
      window.location.pathname
    );
  };

  // Toggle tree expansion
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

  // Toggle description expansion
  const toggleDescription = (nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedDescriptions((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  // Keyboard navigation
  const handleKeyDown = (
    e: React.KeyboardEvent,
    node: SectionNode,
    hasChildren: boolean,
    isExpanded: boolean
  ) => {
    switch (e.key) {
      case "Enter":
      case " ":
        e.preventDefault();
        handleSectionClick(node);
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

  // Render a tree node
  const renderNode = (node: SectionNode, depth: number) => {
    const isExpanded = expandedNodes.has(node.id);
    const hasChildren = node.children.length > 0;
    const hasDescription = Boolean(node.longDescription);
    const isDescriptionExpanded = expandedDescriptions.has(node.id);

    return (
      <TreeNode key={node.id} $depth={depth}>
        <NodeItem
          $hasDescription={hasDescription}
          onClick={() => handleSectionClick(node)}
          onKeyDown={(e) => handleKeyDown(e, node, hasChildren, isExpanded)}
          role="treeitem"
          tabIndex={0}
          aria-expanded={hasChildren ? isExpanded : undefined}
          aria-label={`${node.title}, page ${node.page}${
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
                <ChevronDown size={14} />
              ) : (
                <ChevronRight size={14} />
              ))}
          </ChevronContainer>

          <IconContainer>
            <Hash size={20} />
          </IconContainer>

          <NodeContent>
            <NodeTitle title={node.title}>{node.title}</NodeTitle>
            {hasDescription && (
              <NodeDescription
                className={isDescriptionExpanded ? "expanded" : "collapsed"}
                onClick={(e) => toggleDescription(node.id, e)}
                title={
                  isDescriptionExpanded
                    ? "Click to collapse"
                    : "Click to expand"
                }
              >
                {isDescriptionExpanded ? (
                  <ReactMarkdown>{node.longDescription!}</ReactMarkdown>
                ) : (
                  node.longDescription
                )}
              </NodeDescription>
            )}
          </NodeContent>

          <PageBadge>p. {node.page}</PageBadge>
        </NodeItem>
        {hasChildren && isExpanded && (
          <div role="group">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </TreeNode>
    );
  };

  // Wrapper
  const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) =>
    embedded ? (
      <Container $embedded>{children}</Container>
    ) : (
      <Container>
        <Header>
          <HeaderLeft>
            <Title>
              <BookOpen size={18} />
              Sections
            </Title>
          </HeaderLeft>
        </Header>
        {children}
      </Container>
    );

  if (loading) {
    return (
      <Wrapper>
        <LoadingState>
          <Spinner size="lg" />
          <span>Loading document index...</span>
        </LoadingState>
      </Wrapper>
    );
  }

  if (error) {
    return (
      <Wrapper>
        <ErrorState>
          <AlertTriangle size={32} className="error-icon" />
          <div>Failed to load document index</div>
        </ErrorState>
      </Wrapper>
    );
  }

  if (filteredNodes.length === 0) {
    return null; // No index entries — render nothing so parent can show docs only
  }

  return (
    <Wrapper>
      <TreeContainer>
        {isLimitExceeded && (
          <WarningBanner>
            <AlertTriangle size={16} className="warning-icon" />
            <span className="warning-text">
              This document has more than {DOCUMENT_ANNOTATION_INDEX_LIMIT}{" "}
              index entries. Some sections may not be shown.
            </span>
          </WarningBanner>
        )}
        {hasCircularRefs && (
          <WarningBanner>
            <AlertTriangle size={16} className="warning-icon" />
            <span className="warning-text">
              Circular references detected in section hierarchy.
            </span>
          </WarningBanner>
        )}
        <div role="tree" aria-label="Document sections">
          {filteredNodes.map((node) => renderNode(node, 0))}
        </div>
      </TreeContainer>
    </Wrapper>
  );
};
