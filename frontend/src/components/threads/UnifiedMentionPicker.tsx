import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import styled from "styled-components";
import { User, Database, FileText, Tag } from "lucide-react";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";
import { UnifiedMentionResource } from "./hooks/useUnifiedMentionSearch";

const Container = styled.div`
  position: absolute;
  background: ${color.N1};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  max-height: 400px;
  overflow-y: auto;
  z-index: 1000;
  min-width: 350px;
  max-width: 500px;
`;

const CategoryHeader = styled.div`
  padding: ${spacing.xs} ${spacing.md};
  background: ${color.N2};
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: ${color.N7};
  border-bottom: 1px solid ${color.N4};
  position: sticky;
  top: 0;
  z-index: 1;
`;

const MenuItem = styled.button<{ $isSelected: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: ${spacing.sm};
  width: 100%;
  padding: ${spacing.sm} ${spacing.md};
  border: none;
  background: ${(props) => (props.$isSelected ? color.B1 : "transparent")};
  color: ${color.N10};
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: ${(props) => (props.$isSelected ? color.B1 : color.N2)};
  }

  &:last-child {
    border-radius: 0 0 8px 8px;
  }
`;

const IconContainer = styled.div<{
  $type: "user" | "corpus" | "document" | "annotation";
}>`
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: ${(props) => {
    switch (props.$type) {
      case "user":
        return "linear-gradient(135deg, #667eea 0%, #764ba2 100%)";
      case "corpus":
        return "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)";
      case "document":
        return "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)";
      case "annotation":
        return "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)";
    }
  }};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
  margin-top: 2px;
`;

const ItemInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
`;

const ItemTitle = styled.div`
  font-weight: 600;
  color: ${color.N10};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ItemSubtitle = styled.div`
  font-size: 12px;
  color: ${color.N7};
  font-family: "SF Mono", "Monaco", "Consolas", monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ItemMetadata = styled.div`
  font-size: 11px;
  color: ${color.N6};
  font-style: italic;
`;

const NoResults = styled.div`
  padding: ${spacing.md};
  text-align: center;
  color: ${color.N6};
  font-size: 13px;
`;

const LoadingIndicator = styled.div`
  padding: ${spacing.md};
  text-align: center;
  color: ${color.N6};
  font-size: 13px;
`;

export interface UnifiedMentionPickerProps {
  resources: UnifiedMentionResource[];
  onSelect: (resource: UnifiedMentionResource) => void;
  selectedIndex: number;
  loading?: boolean;
}

export interface UnifiedMentionPickerRef {
  onKeyDown: (event: { event: KeyboardEvent }) => boolean;
}

/**
 * Unified mention picker for all resource types (@user, @corpus, @document, @annotation)
 *
 * PERFORMANCE:
 * - Virtualized rendering for large result sets (future enhancement)
 * - Categorized display reduces visual overwhelm
 * - Keyboard navigation across all categories
 *
 * Part of Issue #623 - @ Mentions Feature (Extended)
 */
export const UnifiedMentionPicker = forwardRef<
  UnifiedMentionPickerRef,
  UnifiedMentionPickerProps
>(({ resources, onSelect, selectedIndex, loading = false }, ref) => {
  const [selected, setSelected] = useState(selectedIndex);

  useEffect(() => {
    setSelected(selectedIndex);
  }, [selectedIndex]);

  useImperativeHandle(ref, () => ({
    onKeyDown: ({ event }: { event: KeyboardEvent }) => {
      if (event.key === "ArrowUp") {
        setSelected((selected - 1 + resources.length) % resources.length);
        return true;
      }

      if (event.key === "ArrowDown") {
        setSelected((selected + 1) % resources.length);
        return true;
      }

      if (event.key === "Enter") {
        if (resources[selected]) {
          onSelect(resources[selected]);
        }
        return true;
      }

      return false;
    },
  }));

  /**
   * Get icon component based on resource type
   */
  const getIcon = (type: UnifiedMentionResource["type"]) => {
    switch (type) {
      case "user":
        return <User size={18} />;
      case "corpus":
        return <Database size={18} />;
      case "document":
        return <FileText size={18} />;
      case "annotation":
        return <Tag size={18} />;
    }
  };

  if (loading && resources.length === 0) {
    return (
      <Container>
        <LoadingIndicator>Searching...</LoadingIndicator>
      </Container>
    );
  }

  if (resources.length === 0) {
    return (
      <Container>
        <NoResults>
          No results found
          <br />
          <small>
            Type to search users, corpuses, documents, and annotations
          </small>
        </NoResults>
      </Container>
    );
  }

  // Group by type for categorized display
  const users = resources.filter((r) => r.type === "user");
  const corpuses = resources.filter((r) => r.type === "corpus");
  const documents = resources.filter((r) => r.type === "document");
  const annotations = resources.filter((r) => r.type === "annotation");

  return (
    <Container>
      {users.length > 0 && (
        <>
          <CategoryHeader>Users</CategoryHeader>
          {users.map((resource) => {
            const globalIndex = resources.indexOf(resource);
            return (
              <MenuItem
                key={resource.id}
                $isSelected={globalIndex === selected}
                onClick={() => onSelect(resource)}
                onMouseEnter={() => setSelected(globalIndex)}
              >
                <IconContainer $type="user">{getIcon("user")}</IconContainer>
                <ItemInfo>
                  <ItemTitle>@{resource.title}</ItemTitle>
                  {resource.subtitle && (
                    <ItemMetadata>{resource.subtitle}</ItemMetadata>
                  )}
                </ItemInfo>
              </MenuItem>
            );
          })}
        </>
      )}

      {corpuses.length > 0 && (
        <>
          <CategoryHeader>Corpuses</CategoryHeader>
          {corpuses.map((resource) => {
            const globalIndex = resources.indexOf(resource);
            return (
              <MenuItem
                key={resource.id}
                $isSelected={globalIndex === selected}
                onClick={() => onSelect(resource)}
                onMouseEnter={() => setSelected(globalIndex)}
              >
                <IconContainer $type="corpus">
                  {getIcon("corpus")}
                </IconContainer>
                <ItemInfo>
                  <ItemTitle>{resource.title}</ItemTitle>
                  {resource.subtitle && (
                    <ItemSubtitle>{resource.subtitle}</ItemSubtitle>
                  )}
                  {resource.metadata && (
                    <ItemMetadata>{resource.metadata}</ItemMetadata>
                  )}
                </ItemInfo>
              </MenuItem>
            );
          })}
        </>
      )}

      {documents.length > 0 && (
        <>
          <CategoryHeader>Documents</CategoryHeader>
          {documents.map((resource) => {
            const globalIndex = resources.indexOf(resource);
            return (
              <MenuItem
                key={resource.id}
                $isSelected={globalIndex === selected}
                onClick={() => onSelect(resource)}
                onMouseEnter={() => setSelected(globalIndex)}
              >
                <IconContainer $type="document">
                  {getIcon("document")}
                </IconContainer>
                <ItemInfo>
                  <ItemTitle>{resource.title}</ItemTitle>
                  {resource.subtitle && (
                    <ItemSubtitle>{resource.subtitle}</ItemSubtitle>
                  )}
                  {resource.metadata && (
                    <ItemMetadata>{resource.metadata}</ItemMetadata>
                  )}
                </ItemInfo>
              </MenuItem>
            );
          })}
        </>
      )}

      {annotations.length > 0 && (
        <>
          <CategoryHeader>Annotations</CategoryHeader>
          {annotations.map((resource) => {
            const globalIndex = resources.indexOf(resource);
            return (
              <MenuItem
                key={resource.id}
                $isSelected={globalIndex === selected}
                onClick={() => onSelect(resource)}
                onMouseEnter={() => setSelected(globalIndex)}
              >
                <IconContainer $type="annotation">
                  {getIcon("annotation")}
                </IconContainer>
                <ItemInfo>
                  <ItemTitle>{resource.title}</ItemTitle>
                  {resource.subtitle && (
                    <ItemSubtitle>{resource.subtitle}</ItemSubtitle>
                  )}
                  {resource.metadata && (
                    <ItemMetadata>{resource.metadata}</ItemMetadata>
                  )}
                </ItemInfo>
              </MenuItem>
            );
          })}
        </>
      )}
    </Container>
  );
});

UnifiedMentionPicker.displayName = "UnifiedMentionPicker";
