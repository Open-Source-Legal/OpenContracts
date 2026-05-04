import React, { useMemo, useEffect, useRef, useState } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { Spinner } from "@os-legal/ui";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  ChevronDown,
  BookOpen,
  AlertTriangle,
  Hash,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

import {
  GET_DOCUMENT_ANNOTATION_INDEX,
  GetDocumentAnnotationIndexOutput,
  GetDocumentAnnotationIndexInput,
  AnnotationIndexNode,
} from "../../graphql/queries";
import { openedCorpus, tocExpandAll } from "../../graphql/cache";
import {
  navigateToRelationshipDocument,
  updateAnnotationSelectionParams,
} from "../../utils/navigationUtils";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import { mediaQuery } from "./styles/corpusDesignTokens";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  DOCUMENT_ANNOTATION_INDEX_MAX_DEPTH,
  OC_SECTION_LABEL,
} from "../../assets/configurations/constants";

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Strip common markdown syntax to produce plain text for collapsed previews.
 * Avoids parsing a full markdown AST for every collapsed node.
 */
function stripMarkdown(text: string): string {
  return (
    text
      // Remove headings: "## Heading" → "Heading"
      .replace(/^#{1,6}\s+/gm, "")
      // Remove bold/italic: **text** or *text* or __text__ or _text_
      .replace(/(\*{1,3}|_{1,3})(.*?)\1/g, "$2")
      // Remove inline code
      .replace(/`([^`]+)`/g, "$1")
      // Remove links: [text](url) → text
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      // Remove images: ![alt](url) → alt
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
      // Remove blockquotes
      .replace(/^>\s+/gm, "")
      // Remove list markers
      .replace(/^[-*+]\s+/gm, "")
      .replace(/^\d+\.\s+/gm, "")
      // Collapse multiple newlines
      .replace(/\n{2,}/g, " ")
      .replace(/\n/g, " ")
      .trim()
  );
}

// ============================================================================
// TYPES
// ============================================================================

interface DocumentAnnotationIndexProps {
  /** Document ID (global relay ID) to fetch annotation index for */
  documentId: string;
  /** Document slug for canonical URL navigation */
  documentSlug?: string;
  /** Optional corpus ID for scoping */
  corpusId?: string;
  /** Maximum tree depth */
  maxDepth?: number;
  /** When true, renders without outer container (for embedding in tabs) */
  embedded?: boolean;
  /**
   * When true, the component is being rendered inside the document page
   * itself, so a section click should only update the `?ann=` selection on
   * the current URL. When false (the default), a click navigates to the
   * document URL with the selection preset — required for corpus-level
   * tables of contents that deep-link into a document.
   */
  onDocumentPage?: boolean;
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
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
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

const EmptyState = styled.div`
  padding: 12px 16px;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-style: italic;
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
// WRAPPER (module-level to avoid React remount anti-pattern)
// ============================================================================

const IndexWrapper: React.FC<{
  embedded?: boolean;
  children: React.ReactNode;
}> = ({ embedded, children }) =>
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

// ============================================================================
// COMPONENT
// ============================================================================

export const DocumentAnnotationIndex: React.FC<
  DocumentAnnotationIndexProps
> = ({
  documentId,
  documentSlug,
  corpusId,
  maxDepth = DOCUMENT_ANNOTATION_INDEX_MAX_DEPTH,
  embedded = false,
  onDocumentPage = false,
  filterQuery,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
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
    fetchPolicy: "cache-first",
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

    // Root nodes: annotations without a parent, or whose parent isn't in the
    // fetched set (orphans).  Orphans are promoted to root so they remain
    // visible, with a console warning to help diagnose tool bugs.
    const rootIds = edges
      .map((e) => e.node.id)
      .filter((id) => {
        if (!hasParent.has(id)) return true;
        const parentId = nodeMap.get(id)?.parent?.id;
        if (parentId && !nodeMap.has(parentId)) {
          console.warn(
            `[DocumentAnnotationIndex] Orphan node "${id}" references missing parent "${parentId}" — promoting to root.`
          );
          return true;
        }
        return false;
      });

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
        longDescription: annot.longDescription ?? undefined,
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
  }, [annotationsData?.annotations?.edges, maxDepth]);

  // Apply filter client-side.  The full tree (up to DOCUMENT_ANNOTATION_INDEX_LIMIT
  // records) must be loaded so we can build the parent→child hierarchy before
  // any filter is applied — server-side filtering would break hierarchy assembly.
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

  // Auto-expand all nodes when a filter is active so matches are visible;
  // collapse back to default when the filter is cleared.
  const prevFilterRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const current = filterQuery?.trim() || "";
    const prev = prevFilterRef.current || "";
    prevFilterRef.current = current;

    if (current && allNodeIds.length > 0) {
      setExpandedNodes(new Set(allNodeIds));
    } else if (!current && prev) {
      // Filter was cleared — collapse back
      setExpandedNodes(new Set());
    }
  }, [filterQuery, allNodeIds]);

  const handleSectionClick = (node: SectionNode) => {
    if (onDocumentPage) {
      // Already on the document page — update ?ann= to select the annotation.
      // CentralRouteManager will sync selectedAnnotationIds, triggering scroll.
      updateAnnotationSelectionParams(location, navigate, {
        annotationIds: [node.id],
      });
    } else {
      // Corpus-level TOC — navigate to the document page with annotation selected
      const corpus = openedCorpus();
      navigateToRelationshipDocument(
        { id: documentId, title: node.title, slug: documentSlug },
        corpus,
        navigate,
        window.location.pathname,
        { annotationIds: [node.id] }
      );
    }
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

  // Keyboard navigation (WAI-ARIA TreeView pattern)
  const handleKeyDown = (
    e: React.KeyboardEvent,
    node: SectionNode,
    hasChildren: boolean,
    isExpanded: boolean
  ) => {
    const moveFocus = (direction: "up" | "down") => {
      const tree = (e.currentTarget as HTMLElement).closest('[role="tree"]');
      if (!tree) return;
      const items = Array.from(
        tree.querySelectorAll<HTMLElement>('[role="treeitem"]')
      );
      const idx = items.indexOf(e.currentTarget as HTMLElement);
      const target = direction === "down" ? items[idx + 1] : items[idx - 1];
      target?.focus();
    };

    switch (e.key) {
      case "Enter":
      case " ":
        e.preventDefault();
        handleSectionClick(node);
        break;
      case "ArrowDown":
        e.preventDefault();
        moveFocus("down");
        break;
      case "ArrowUp":
        e.preventDefault();
        moveFocus("up");
        break;
      case "ArrowRight":
        e.preventDefault();
        if (hasChildren && !isExpanded) {
          setExpandedNodes((prev) => new Set(prev).add(node.id));
        } else if (hasChildren && isExpanded) {
          // Already expanded — move focus to first child
          moveFocus("down");
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
        } else {
          // Collapsed or leaf — move focus to parent treeitem
          const parentGroup = (e.currentTarget as HTMLElement).closest(
            '[role="group"]'
          );
          if (parentGroup) {
            const parentItem =
              parentGroup.previousElementSibling as HTMLElement | null;
            parentItem?.focus();
          }
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
                  <ReactMarkdown rehypePlugins={[rehypeSanitize]}>
                    {node.longDescription!}
                  </ReactMarkdown>
                ) : (
                  stripMarkdown(node.longDescription!)
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

  if (loading) {
    return (
      <IndexWrapper embedded={embedded}>
        <LoadingState>
          <Spinner size="lg" />
          <span>Loading document index...</span>
        </LoadingState>
      </IndexWrapper>
    );
  }

  if (error) {
    return (
      <IndexWrapper embedded={embedded}>
        <ErrorState>
          <AlertTriangle size={32} className="error-icon" />
          <div>Failed to load document index</div>
        </ErrorState>
      </IndexWrapper>
    );
  }

  if (filteredNodes.length === 0) {
    // When embedded inside the TOC tree, show a subtle empty state so
    // the expand chevron isn't a silent no-op.
    if (embedded) {
      return (
        <EmptyState>
          {filterQuery
            ? "No matching sections"
            : "No indexed sections for this document"}
        </EmptyState>
      );
    }
    return null;
  }

  return (
    <IndexWrapper embedded={embedded}>
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
        <div
          role={embedded ? "group" : "tree"}
          aria-label={embedded ? undefined : "Document sections"}
        >
          {filteredNodes.map((node) => renderNode(node, 0))}
        </div>
      </TreeContainer>
    </IndexWrapper>
  );
};
