import React, { useState, useCallback, useMemo } from "react";
import { useQuery, useMutation } from "@apollo/client";
import styled from "styled-components";
import { Button, Dropdown, IconButton, Spinner } from "@os-legal/ui";
import { AlertCircle, StickyNote } from "lucide-react";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import { toast } from "react-toastify";
import {
  Link2,
  FileText,
  Trash2,
  ChevronRight,
  Filter,
  RefreshCw,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  GET_DOCUMENT_RELATIONSHIPS,
  GetDocumentRelationshipsOutput,
  GetDocumentRelationshipsInput,
  DocumentRelationshipNode,
} from "../../graphql/queries";
import {
  DELETE_DOCUMENT_RELATIONSHIP,
  DeleteDocumentRelationshipInputs,
  DeleteDocumentRelationshipOutputs,
} from "../../graphql/mutations";
import { openedCorpus } from "../../graphql/cache";
import { navigateToRelationshipDocument } from "../../utils/navigationUtils";
import { getPermissions } from "../../utils/transform";
import { getCreatorDisplay } from "../../utils/userDisplay";
import { PermissionTypes } from "../types";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
} from "../../assets/configurations/osLegalStyles";
import { DOCUMENT_RELATIONSHIP_PAGINATION_LIMIT } from "../../assets/configurations/constants";
import { formatDistanceToNow } from "date-fns";
import { DEFAULT_LABEL_COLOR } from "../../assets/configurations/constants";

// ============================================================================
// UTILITIES
// ============================================================================

/**
 * Validates and sanitizes a color string to prevent CSS injection.
 * Only allows valid hex colors (3 or 6 chars, with or without #).
 * Returns a safe default color if validation fails.
 *
 * SECURITY NOTE: This is defense-in-depth. The backend GraphQL mutations
 * should also validate color values before storage. If invalid colors are
 * detected here, investigate the source and consider adding backend
 * validation to the AnnotationLabel mutation.
 */
function sanitizeColor(color: string | null | undefined): string {
  if (!color) return `#${DEFAULT_LABEL_COLOR}`;

  // Remove # prefix if present for validation
  const colorWithoutHash = color.replace(/^#/, "");

  // Validate: must be 3 or 6 hex characters only
  if (/^[0-9A-Fa-f]{3}$/.test(colorWithoutHash)) {
    return `#${colorWithoutHash}`;
  }
  if (/^[0-9A-Fa-f]{6}$/.test(colorWithoutHash)) {
    return `#${colorWithoutHash}`;
  }

  // Log warning for invalid color - helps identify data quality issues
  console.warn(`[sanitizeColor] Invalid color value rejected: "${color}"`);
  return `#${DEFAULT_LABEL_COLOR}`;
}

// ============================================================================
// TYPES
// ============================================================================

interface CorpusDocumentRelationshipsProps {
  corpusId: string;
}

type FilterType = "ALL" | "RELATIONSHIP" | "NOTES";

// ============================================================================
// STYLED COMPONENTS
// ============================================================================

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  background: ${OS_LEGAL_COLORS.surface};
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
`;

const Title = styled.h2`
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const FilterBar = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const TableContainer = styled.div`
  flex: 1;
  overflow: auto;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  background: white;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;

  th,
  td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }

  th {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: ${OS_LEGAL_COLORS.textSecondary};
    position: sticky;
    top: 0;
    z-index: 1;
  }

  tbody tr {
    transition: background-color 0.15s ease;

    &:hover {
      background: ${OS_LEGAL_COLORS.surfaceHover};
    }
  }
`;

const DocumentLink = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  padding: 4px 8px;
  margin: -4px -8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.accent};
  transition: all 0.15s ease;
  max-width: 200px;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.accentHover};
  }

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;

const RelationshipArrow = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const TypeBadge = styled.span<{ $type: "RELATIONSHIP" | "NOTES" }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  background: ${(props) =>
    props.$type === "RELATIONSHIP" ? OS_LEGAL_COLORS.blueBorder : "#fef3c7"};
  color: ${(props) =>
    props.$type === "RELATIONSHIP" ? OS_LEGAL_COLORS.blueDark : "#92400e"};
`;

const LabelBadge = styled.span<{ $color: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  background: ${(props) => props.$color}20;
  color: ${(props) => props.$color};
  border: 1px solid ${(props) => props.$color}40;
`;

const CreatorCell = styled.div`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const DateCell = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const ActionButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.dangerBorderHover};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 16px;
  text-align: center;
  color: ${OS_LEGAL_COLORS.textMuted};

  svg {
    margin-bottom: 16px;
    opacity: 0.5;
  }

  h3 {
    margin: 0 0 8px 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  p {
    margin: 0;
    font-size: 0.875rem;
  }
`;

const LoadingState = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 64px 16px;
  color: ${OS_LEGAL_COLORS.textMuted};
  gap: 8px;
`;

const TotalCount = styled.div`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 12px;
`;

// ============================================================================
// COMPONENT
// ============================================================================

export const CorpusDocumentRelationships: React.FC<
  CorpusDocumentRelationshipsProps
> = ({ corpusId }) => {
  const navigate = useNavigate();
  const [filterType, setFilterType] = useState<FilterType>("ALL");
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Query for document relationships
  const { data, loading, error, refetch } = useQuery<
    GetDocumentRelationshipsOutput,
    GetDocumentRelationshipsInput
  >(GET_DOCUMENT_RELATIONSHIPS, {
    variables: {
      corpusId,
      first: DOCUMENT_RELATIONSHIP_PAGINATION_LIMIT,
    },
    skip: !corpusId,
    fetchPolicy: "cache-and-network",
  });

  // Delete mutation
  const [deleteRelationship, { loading: deleteLoading }] = useMutation<
    DeleteDocumentRelationshipOutputs,
    DeleteDocumentRelationshipInputs
  >(DELETE_DOCUMENT_RELATIONSHIP, {
    refetchQueries: [
      {
        query: GET_DOCUMENT_RELATIONSHIPS,
        variables: { corpusId },
      },
    ],
  });

  // Get relationships from query
  const relationships = useMemo(() => {
    const edges = data?.documentRelationships?.edges || [];
    let filtered = edges.map((e) => e.node);

    // Apply type filter
    if (filterType !== "ALL") {
      filtered = filtered.filter((r) => r.relationshipType === filterType);
    }

    return filtered;
  }, [data, filterType]);

  const totalCount = data?.documentRelationships?.totalCount ?? 0;

  // Handle document navigation - uses shared utility for type safety
  const handleDocumentClick = useCallback(
    (doc: { id: string; title: string; slug?: string }) => {
      const corpus = openedCorpus();
      navigateToRelationshipDocument(
        doc,
        corpus,
        navigate,
        window.location.pathname
      );
    },
    [navigate]
  );

  // Handle delete
  const handleDelete = useCallback(
    async (relationshipId: string) => {
      try {
        const result = await deleteRelationship({
          variables: { documentRelationshipId: relationshipId },
        });

        if (result.data?.deleteDocumentRelationship?.ok) {
          toast.success("Relationship deleted");
        } else {
          toast.error(
            result.data?.deleteDocumentRelationship?.message ||
              "Failed to delete relationship"
          );
        }
      } catch (err: unknown) {
        console.error("Error deleting relationship:", err);
        // Extract GraphQL error message if available for better UX
        let errorMessage = "Failed to delete relationship";
        if (
          err &&
          typeof err === "object" &&
          "graphQLErrors" in err &&
          Array.isArray((err as { graphQLErrors: unknown[] }).graphQLErrors)
        ) {
          const gqlError = (err as { graphQLErrors: { message?: string }[] })
            .graphQLErrors[0]?.message;
          if (gqlError) {
            errorMessage = gqlError;
          }
        }
        toast.error(errorMessage);
      } finally {
        setDeleteConfirm(null);
      }
    },
    [deleteRelationship]
  );

  // Check permissions
  const canDelete = useCallback((relationship: DocumentRelationshipNode) => {
    const perms = getPermissions(relationship.myPermissions ?? []);
    return perms.includes(PermissionTypes.CAN_REMOVE);
  }, []);

  // Filter options for dropdown
  const filterOptions = [
    { value: "ALL", label: "All Types" },
    { value: "RELATIONSHIP", label: "Labeled Relationships" },
    { value: "NOTES", label: "Notes" },
  ];

  if (error) {
    return (
      <Container>
        <EmptyState>
          <AlertCircle size={48} strokeWidth={1.5} />
          <h3>Error Loading Relationships</h3>
          <p>{error.message}</p>
          <Button
            onClick={() => refetch()}
            style={{ marginTop: 16 }}
            variant="secondary"
            leftIcon={<RefreshCw size={14} />}
          >
            Retry
          </Button>
        </EmptyState>
      </Container>
    );
  }

  return (
    <Container>
      <Header>
        <Title>
          <Link2 size={20} />
          Document Relationships
        </Title>
        <FilterBar>
          <Dropdown
            mode="select"
            options={filterOptions}
            value={filterType}
            onChange={(value) => setFilterType(value as FilterType)}
            clearable={false}
          />
          <IconButton
            variant="ghost"
            onClick={() => refetch()}
            loading={loading}
            aria-label="Refresh"
          >
            <RefreshCw size={16} />
          </IconButton>
        </FilterBar>
      </Header>

      <TableContainer>
        {loading && !data ? (
          <LoadingState>
            <Spinner size="sm" />
            Loading relationships...
          </LoadingState>
        ) : relationships.length === 0 ? (
          <EmptyState>
            <Link2 size={48} strokeWidth={1.5} />
            <h3>No Document Relationships</h3>
            <p>
              {filterType !== "ALL"
                ? `No ${filterType.toLowerCase()} relationships found. Try changing the filter.`
                : "Create relationships between documents using the toolbar or context menu."}
            </p>
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <th>Source Document</th>
                <th style={{ width: 40 }}></th>
                <th>Target Document</th>
                <th>Type</th>
                <th>Label</th>
                <th>Creator</th>
                <th>Created</th>
                <th style={{ width: 50 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {relationships.map((rel) => (
                <tr key={rel.id}>
                  <td>
                    <DocumentLink
                      onClick={() => handleDocumentClick(rel.sourceDocument)}
                      title={rel.sourceDocument.title}
                    >
                      <FileText size={14} />
                      <span>{rel.sourceDocument.title}</span>
                    </DocumentLink>
                  </td>
                  <td>
                    <RelationshipArrow>
                      <ChevronRight size={16} />
                    </RelationshipArrow>
                  </td>
                  <td>
                    <DocumentLink
                      onClick={() => handleDocumentClick(rel.targetDocument)}
                      title={rel.targetDocument.title}
                    >
                      <FileText size={14} />
                      <span>{rel.targetDocument.title}</span>
                    </DocumentLink>
                  </td>
                  <td>
                    <TypeBadge
                      $type={
                        rel.relationshipType === "RELATIONSHIP"
                          ? "RELATIONSHIP"
                          : "NOTES"
                      }
                    >
                      {rel.relationshipType === "RELATIONSHIP" ? (
                        <>
                          <Link2 size={12} />
                          Relationship
                        </>
                      ) : (
                        <>
                          <StickyNote size={12} />
                          Notes
                        </>
                      )}
                    </TypeBadge>
                  </td>
                  <td>
                    {rel.annotationLabel ? (
                      <LabelBadge
                        $color={sanitizeColor(rel.annotationLabel.color)}
                      >
                        {rel.annotationLabel.text}
                      </LabelBadge>
                    ) : (
                      <span style={{ color: OS_LEGAL_COLORS.textMuted }}>
                        —
                      </span>
                    )}
                  </td>
                  <td>
                    <CreatorCell>{getCreatorDisplay(rel.creator)}</CreatorCell>
                  </td>
                  <td>
                    <DateCell>
                      {rel.created
                        ? formatDistanceToNow(new Date(rel.created), {
                            addSuffix: true,
                          })
                        : "—"}
                    </DateCell>
                  </td>
                  <td>
                    {canDelete(rel) && (
                      <ActionButton
                        onClick={() => setDeleteConfirm(rel.id)}
                        disabled={deleteLoading}
                        title="Delete relationship"
                      >
                        <Trash2 size={14} />
                      </ActionButton>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </TableContainer>

      {totalCount > 0 && (
        <TotalCount>
          Showing {relationships.length} of {totalCount} relationship
          {totalCount !== 1 ? "s" : ""}
        </TotalCount>
      )}

      <ConfirmModal
        visible={deleteConfirm !== null}
        message="Are you sure you want to delete this document relationship? This action cannot be undone."
        yesAction={() => deleteConfirm && handleDelete(deleteConfirm)}
        noAction={() => setDeleteConfirm(null)}
        toggleModal={() => setDeleteConfirm(null)}
      />
    </Container>
  );
};

export default CorpusDocumentRelationships;
