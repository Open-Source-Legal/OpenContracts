import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import styled from "styled-components";
import { Database, FileText } from "lucide-react";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const Container = styled.div`
  position: absolute;
  background: ${color.N1};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  max-height: 300px;
  overflow-y: auto;
  z-index: 1000;
  min-width: 300px;
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

  &:first-child {
    border-radius: 8px 8px 0 0;
  }

  &:last-child {
    border-radius: 0 0 8px 8px;
  }
`;

const IconContainer = styled.div<{ $type: "corpus" | "document" }>`
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: ${(props) =>
    props.$type === "corpus"
      ? "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
      : "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"};
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

const ItemMeta = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const ItemPath = styled.span`
  font-size: 12px;
  color: ${color.N7};
  font-family: "SF Mono", "Monaco", "Consolas", monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ItemContext = styled.span`
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

const TypeHeader = styled.div`
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

export interface MentionResource {
  id: string;
  slug: string;
  title: string;
  type: "corpus" | "document";
  creator: {
    slug: string;
  };
  // For documents, may have corpus info
  corpus?: {
    slug: string;
    title: string;
    creator: {
      slug: string;
    };
  };
}

export interface ResourceMentionPickerProps {
  resources: MentionResource[];
  onSelect: (resource: MentionResource) => void;
  selectedIndex: number;
}

export interface ResourceMentionPickerRef {
  onKeyDown: (event: { event: KeyboardEvent }) => boolean;
}

/**
 * Resource mention picker for @corpus: and @document: autocomplete
 * Used with TipTap's Mention extension for cross-referencing resources
 *
 * Security: Backend filters results via .visible_to_user() - frontend trusts the data
 * Part of Issue #623 - @ Mentions Feature
 */
export const ResourceMentionPicker = forwardRef<
  ResourceMentionPickerRef,
  ResourceMentionPickerProps
>(({ resources, onSelect, selectedIndex }, ref) => {
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
   * Generate mention string format based on resource type
   * Formats:
   * - Corpus: @corpus:slug
   * - Document (no corpus): @document:slug
   * - Document (in corpus): @corpus:corpus-slug/document:doc-slug
   */
  const getMentionFormat = (resource: MentionResource): string => {
    if (resource.type === "corpus") {
      return `@corpus:${resource.slug}`;
    }

    // Document
    if (resource.corpus) {
      return `@corpus:${resource.corpus.slug}/document:${resource.slug}`;
    }

    return `@document:${resource.slug}`;
  };

  if (resources.length === 0) {
    return (
      <Container>
        <NoResults>
          No resources found
          <br />
          <small>Type to search corpuses and documents</small>
        </NoResults>
      </Container>
    );
  }

  // Group by type for better UX
  const corpuses = resources.filter((r) => r.type === "corpus");
  const documents = resources.filter((r) => r.type === "document");

  return (
    <Container>
      {corpuses.length > 0 && (
        <>
          <TypeHeader>Corpuses</TypeHeader>
          {corpuses.map((resource, index) => {
            const globalIndex = index;
            return (
              <MenuItem
                key={resource.id}
                $isSelected={globalIndex === selected}
                onClick={() => onSelect(resource)}
                onMouseEnter={() => setSelected(globalIndex)}
              >
                <IconContainer $type="corpus">
                  <Database size={18} />
                </IconContainer>
                <ItemInfo>
                  <ItemTitle>{resource.title}</ItemTitle>
                  <ItemMeta>
                    <ItemPath>{getMentionFormat(resource)}</ItemPath>
                    <ItemContext>by @{resource.creator.slug}</ItemContext>
                  </ItemMeta>
                </ItemInfo>
              </MenuItem>
            );
          })}
        </>
      )}

      {documents.length > 0 && (
        <>
          <TypeHeader>Documents</TypeHeader>
          {documents.map((resource, index) => {
            const globalIndex = corpuses.length + index;
            return (
              <MenuItem
                key={resource.id}
                $isSelected={globalIndex === selected}
                onClick={() => onSelect(resource)}
                onMouseEnter={() => setSelected(globalIndex)}
              >
                <IconContainer $type="document">
                  <FileText size={18} />
                </IconContainer>
                <ItemInfo>
                  <ItemTitle>{resource.title}</ItemTitle>
                  <ItemMeta>
                    <ItemPath>{getMentionFormat(resource)}</ItemPath>
                    {resource.corpus && (
                      <ItemContext>
                        in "{resource.corpus.title}" by @{resource.creator.slug}
                      </ItemContext>
                    )}
                    {!resource.corpus && (
                      <ItemContext>by @{resource.creator.slug}</ItemContext>
                    )}
                  </ItemMeta>
                </ItemInfo>
              </MenuItem>
            );
          })}
        </>
      )}
    </Container>
  );
});

ResourceMentionPicker.displayName = "ResourceMentionPicker";
