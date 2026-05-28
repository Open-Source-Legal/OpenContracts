import React, { useState, useCallback } from "react";
import { Input, Spinner, ScrollArea } from "@os-legal/ui";
import { Search, FileText, Tag } from "lucide-react";
import {
  SectionTitle,
  CorpusCard,
  CorpusCardHeader,
  CorpusCardIcon,
  CorpusCardTitle,
  CorpusCardDescription,
  CorpusCardMeta,
  EmptyState,
} from "../UploadModalStyles";
import { CorpusType } from "../../../../../types/graphql-api";

interface CorpusSelectorCardProps {
  corpuses: CorpusType[];
  selectedCorpus: CorpusType | null;
  onSelect: (corpus: CorpusType | null) => void;
  onSearchChange: (term: string) => void;
  searchTerm: string;
  loading?: boolean;
  disabled?: boolean;
}

/**
 * Card-based corpus selector with search functionality.
 * Shows a list of corpuses the user can add documents to.
 */
export const CorpusSelectorCard: React.FC<CorpusSelectorCardProps> = ({
  corpuses,
  selectedCorpus,
  onSelect,
  onSearchChange,
  searchTerm,
  loading = false,
  disabled = false,
}) => {
  const [localSearchTerm, setLocalSearchTerm] = useState(searchTerm);

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setLocalSearchTerm(value);
      onSearchChange(value);
    },
    [onSearchChange]
  );

  const handleCorpusClick = useCallback(
    (corpus: CorpusType) => {
      if (disabled) return;
      // Toggle selection if clicking the same corpus
      if (selectedCorpus?.id === corpus.id) {
        onSelect(null);
      } else {
        onSelect(corpus);
      }
    },
    [selectedCorpus, onSelect, disabled]
  );

  return (
    <div>
      <SectionTitle>
        <FileText />
        Select Corpus
      </SectionTitle>

      {/* Search input */}
      <div style={{ marginBottom: "var(--oc-spacing-md)" }}>
        <Input
          id="corpus-search"
          placeholder="Search corpuses..."
          value={localSearchTerm}
          onChange={handleSearchChange}
          disabled={disabled}
          size="lg"
          fullWidth
          leftIcon={<Search style={{ width: 16, height: 16 }} />}
        />
      </div>

      {/* Corpus list */}
      <ScrollArea style={{ maxHeight: "300px" }}>
        {loading ? (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              padding: "var(--oc-spacing-xl)",
            }}
          >
            <Spinner size={24} />
          </div>
        ) : corpuses.length === 0 ? (
          <EmptyState>
            <FileText />
            <div className="title">No corpuses found</div>
            <div className="description">
              {localSearchTerm
                ? "Try a different search term"
                : "You don't have any corpuses you can add to"}
            </div>
          </EmptyState>
        ) : (
          corpuses.map((corpus) => (
            <CorpusCard
              key={corpus.id}
              $selected={selectedCorpus?.id === corpus.id}
              onClick={() => handleCorpusClick(corpus)}
              role="button"
              tabIndex={0}
              aria-selected={selectedCorpus?.id === corpus.id}
            >
              <CorpusCardHeader>
                {corpus.icon && <CorpusCardIcon src={corpus.icon} alt="" />}
                <CorpusCardTitle>{corpus.title}</CorpusCardTitle>
              </CorpusCardHeader>
              {(corpus.descriptionPreview || corpus.description) && (
                <CorpusCardDescription>
                  {corpus.descriptionPreview || corpus.description}
                </CorpusCardDescription>
              )}
              <CorpusCardMeta>
                <span>
                  <FileText />
                  {corpus.documentCount || 0} documents
                </span>
                {corpus.labelSet?.title && (
                  <span>
                    <Tag />
                    {corpus.labelSet.title}
                  </span>
                )}
              </CorpusCardMeta>
            </CorpusCard>
          ))
        )}
      </ScrollArea>
    </div>
  );
};

export default CorpusSelectorCard;
