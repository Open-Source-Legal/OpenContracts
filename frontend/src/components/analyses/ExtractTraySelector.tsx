import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Fuse from "fuse.js";
import { SearchInput } from "@os-legal/ui";
import { ExtractType } from "../../types/graphql-api";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import { useCorpusState } from "../annotator/context/CorpusAtom";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../annotator/hooks/AnalysisHooks";
import { ExtractItem } from "../extracts/ExtractItem";
import styled from "styled-components";

/**
 * Props for ExtractTraySelector.
 */
interface ExtractTraySelectorProps {
  /** Determines if the selector should be read-only */
  read_only: boolean;
  /** The list of available extracts */
  extracts: ExtractType[];
}

const TrayContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
  border: none;
  box-shadow: none;
  background: transparent;
  overflow: hidden;
`;

const SearchSection = styled.div`
  flex: 0 0 auto;
  padding: 1.25rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-bottom: none;
  border-radius: 12px 12px 0 0;
  z-index: 1;

  .ui.input {
    width: 100%;

    input {
      border-radius: 10px;
      border: 1px solid #e2e8f0;
      padding: 0.75rem 1rem;
      font-size: 0.875rem;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);

      &::placeholder {
        color: #94a3b8;
      }

      &:focus {
        border-color: #4a90e2;
        box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.08);
      }
    }

    i.icon {
      font-size: 1rem;
      color: #64748b;
      opacity: 0.7;
      transition: all 0.2s ease;

      &:hover {
        opacity: 1;
        color: #4a90e2;
      }
    }
  }
`;

const ExtractListSection = styled.div`
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0 0 12px 12px;
  padding: 1rem;

  &::-webkit-scrollbar {
    width: 4px;
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(74, 144, 226, 0.15);
    border-radius: 2px;

    &:hover {
      background: rgba(74, 144, 226, 0.25);
    }
  }
`;

const EmptyStateContainer = styled.div`
  margin: 2rem 0;
  padding: 2.5rem;
  text-align: center;
  background: linear-gradient(165deg, #f8fafc, #fff);
  border: 1px dashed #e2e8f0;
  border-radius: 16px;
  box-shadow: none;

  h4 {
    color: #1e293b;
    font-size: 1.125rem;
    font-weight: 600;
    margin-bottom: 0.75rem;
  }

  p {
    color: #64748b;
    font-size: 0.875rem;
    line-height: 1.5;
    max-width: 24rem;
    margin: 0 auto;
  }
`;

/**
 * A vertical tray selector for extracts.
 *
 * Provides fuzzy search and lists available extracts.
 */
const ExtractTraySelector: React.FC<ExtractTraySelectorProps> = ({
  read_only,
  extracts,
}) => {
  const { width } = useWindowDimensions();
  const { selectedCorpus } = useCorpusState();
  const { selectedExtract, setSelectedExtract } = useAnalysisSelection();
  const { onSelectExtract } = useAnalysisManager();

  const [searchTerm, setSearchTerm] = useState<string>("");

  // Fuse configuration options for fuzzy matching.
  const fuseOptions = useMemo(
    () => ({
      keys: ["name", "description"],
      threshold: 0.4,
    }),
    []
  );

  const extractsFuse = useMemo(
    () => new Fuse(extracts, fuseOptions),
    [extracts, fuseOptions]
  );

  const filteredItems = useMemo((): ExtractType[] => {
    if (!searchTerm) return extracts;
    return extractsFuse.search(searchTerm).map((result) => result.item);
  }, [extracts, searchTerm, extractsFuse]);

  const handleSearchChange = (value: string) => setSearchTerm(value);

  const mountedRef = useRef<boolean>(false);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const renderItems = useCallback(() => {
    if (filteredItems.length === 0) {
      return (
        <EmptyStateContainer key="no_extracts_placeholder">
          <h4>No Extracts Available</h4>
          <p>
            If you have sufficient privileges, try creating a new extract from
            the corpus page.
          </p>
        </EmptyStateContainer>
      );
    }
    return filteredItems.map((item) => (
      <ExtractItem
        key={item.id}
        corpus={selectedCorpus}
        compact={width <= 768}
        extract={item}
        selected={Boolean(selectedExtract && item.id === selectedExtract.id)}
        read_only={read_only}
        onSelect={() => {
          onSelectExtract(
            selectedExtract && item.id === selectedExtract.id ? null : item
          );
        }}
      />
    ));
  }, [
    filteredItems,
    width,
    read_only,
    selectedExtract,
    selectedCorpus,
    onSelectExtract,
  ]);

  return (
    <TrayContainer>
      <SearchSection>
        <SearchInput
          placeholder="Search for extracts..."
          onChange={(e) => handleSearchChange(e.target.value)}
          value={searchTerm}
          onClear={searchTerm ? () => handleSearchChange("") : undefined}
        />
      </SearchSection>
      <ExtractListSection>
        {mountedRef.current && renderItems()}
      </ExtractListSection>
    </TrayContainer>
  );
};

export default ExtractTraySelector;
