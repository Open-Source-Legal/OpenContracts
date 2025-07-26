import React, { useState, useEffect } from "react";
import { useQuery, useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  Database,
  ChevronDown,
  Plus,
  Edit3,
  Search,
  X,
  Loader2,
} from "lucide-react";
import {
  GET_FIELDSETS,
  GetFieldsetsInputs,
  GetFieldsetsOutputs,
} from "../../../graphql/queries";
import { FieldsetType } from "../../../types/graphql-api";
import { FieldsetModal } from "../modals/FieldsetModal";
import _ from "lodash";

// Styled Components
const Container = styled.div`
  position: relative;
  width: 100%;
`;

const SelectButton = styled.button<{ $hasValue: boolean; $isOpen: boolean }>`
  width: 100%;
  padding: 0.75rem 1rem;
  border: 1.5px solid ${(props) => (props.$isOpen ? "#3b82f6" : "#e2e8f0")};
  border-radius: 10px;
  font-size: 0.9375rem;
  background: white;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: space-between;
  text-align: left;
  color: ${(props) => (props.$hasValue ? "#0f172a" : "#94a3b8")};
  font-weight: ${(props) => (props.$hasValue ? "500" : "400")};
  min-height: 44px;
  box-shadow: ${(props) =>
    props.$isOpen ? "0 0 0 3.5px rgba(59, 130, 246, 0.12)" : "none"};

  &:hover:not(:disabled) {
    border-color: ${(props) => (props.$isOpen ? "#3b82f6" : "#cbd5e1")};
    background: ${(props) => (props.$isOpen ? "white" : "#fafbfc")};
  }

  &:focus {
    outline: none;
  }

  &:disabled {
    background: #f8fafc;
    cursor: not-allowed;
    opacity: 0.6;
  }
`;

const SelectText = styled.span`
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const SelectIcon = styled(ChevronDown)<{ $isOpen: boolean }>`
  width: 18px;
  height: 18px;
  color: #64748b;
  transition: transform 0.2s ease;
  transform: ${(props) => (props.$isOpen ? "rotate(180deg)" : "rotate(0)")};
  flex-shrink: 0;
`;

const DropdownContainer = styled(motion.div)`
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: white;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.1);
  z-index: 50;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const SearchInputWrapper = styled.div`
  padding: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
  position: relative;
`;

const StyledSearchInput = styled.input`
  width: 100%;
  padding: 0.5rem 2.25rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 0.875rem;
  transition: all 0.2s ease;
  background: #fafbfc;

  &:focus {
    outline: none;
    border-color: #3b82f6;
    background: white;
  }

  &::placeholder {
    color: #94a3b8;
  }
`;

const SearchIconWrapper = styled.div`
  position: absolute;
  left: 1.25rem;
  top: 50%;
  transform: translateY(-50%);
  color: #64748b;
  pointer-events: none;
`;

const ClearButton = styled.button`
  position: absolute;
  right: 1.25rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  color: #64748b;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  &:hover {
    background: #e2e8f0;
    color: #475569;
  }
`;

const OptionsContainer = styled.div`
  max-height: 180px;
  overflow-y: auto;
  padding: 0.5rem;

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: #e2e8f0;
    border-radius: 2px;

    &:hover {
      background: #cbd5e1;
    }
  }
`;

const OptionsSection = styled.div`
  &:not(:last-child) {
    margin-bottom: 0.25rem;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid #f1f5f9;
  }
`;

const SectionLabel = styled.div`
  font-size: 0.6875rem;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.25rem 0.5rem;
`;

const Option = styled(motion.button)`
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  border-radius: 6px;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.875rem;

  &:hover {
    background: #f1f5f9;
  }

  &:focus {
    outline: none;
    background: #e0f2fe;
  }
`;

const OptionText = styled.div`
  flex: 1;
  min-width: 0;
`;

const OptionName = styled.div`
  font-weight: 500;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const OptionDescription = styled.div`
  font-size: 0.75rem;
  color: #64748b;
  margin-top: 0.125rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const CreateOption = styled(Option)`
  color: #3b82f6;
  font-weight: 500;

  &:hover {
    background: #eff6ff;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const EditButton = styled(motion.button)`
  padding: 0.25rem;
  border: none;
  background: none;
  cursor: pointer;
  color: #64748b;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  flex-shrink: 0;

  &:hover {
    background: #dbeafe;
    color: #2563eb;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const LoadingContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem;
  color: #64748b;
  font-size: 0.875rem;
  gap: 0.75rem;
`;

const EmptyState = styled.div`
  padding: 2rem 1rem;
  text-align: center;
  color: #64748b;
  font-size: 0.8125rem;
  line-height: 1.4;
`;

const InfoBox = styled(motion.div)`
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 10px;
  padding: 0.875rem 1rem;
  margin-top: 0.75rem;
  display: flex;
  gap: 0.75rem;
  font-size: 0.8125rem;

  svg {
    width: 18px;
    height: 18px;
    color: #0284c7;
    flex-shrink: 0;
    margin-top: 0.125rem;
  }
`;

const InfoContent = styled.div`
  flex: 1;
`;

const InfoTitle = styled.h4`
  margin: 0 0 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #0c4a6e;
`;

const InfoDescription = styled.p`
  margin: 0;
  font-size: 0.75rem;
  color: #075985;
  line-height: 1.4;
`;

interface UnifiedFieldsetSelectorProps {
  value?: FieldsetType | null;
  onChange: (fieldset: FieldsetType | null) => void;
  placeholder?: string;
  disabled?: boolean;
  showInfo?: boolean;
}

export const UnifiedFieldsetSelector: React.FC<
  UnifiedFieldsetSelectorProps
> = ({
  value,
  onChange,
  placeholder = "Search or select a fieldset...",
  disabled = false,
  showInfo = true,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [localSearchQuery, setLocalSearchQuery] = useState("");
  const [showFieldsetModal, setShowFieldsetModal] = useState(false);
  const [editingFieldset, setEditingFieldset] = useState<FieldsetType | null>(
    null
  );

  const { loading, data, refetch, error } = useQuery<
    GetFieldsetsOutputs,
    GetFieldsetsInputs
  >(GET_FIELDSETS, {
    variables: searchQuery ? { searchText: searchQuery } : {},
    fetchPolicy: "cache-and-network",
    notifyOnNetworkStatusChange: true,
  });

  const debouncedSetSearchQuery = React.useCallback(
    _.debounce((query: string) => {
      setSearchQuery(query);
    }, 300),
    []
  );

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setLocalSearchQuery(query);
    debouncedSetSearchQuery(query);
  };

  const handleSelect = (fieldset: FieldsetType) => {
    onChange(fieldset);
    setIsOpen(false);
    setSearchQuery("");
    setLocalSearchQuery("");
  };

  const handleCreateNew = () => {
    setEditingFieldset(null);
    setShowFieldsetModal(true);
    setIsOpen(false);
  };

  const handleEdit = (fieldset: FieldsetType, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingFieldset(fieldset);
    setShowFieldsetModal(true);
  };

  const handleFieldsetCreated = async (newFieldset: any) => {
    await refetch();
    if (!editingFieldset) {
      onChange(newFieldset);
    }
    setShowFieldsetModal(false);
    setEditingFieldset(null);
  };

  const handleClearSearch = () => {
    setLocalSearchQuery("");
    setSearchQuery("");
    debouncedSetSearchQuery("");
  };

  const fieldsets = data?.fieldsets.edges.map((edge) => edge.node) || [];

  // Show first 5 fieldsets when no search, all when searching
  const displayFieldsets = localSearchQuery ? fieldsets : fieldsets.slice(0, 5);
  const hasMore = !localSearchQuery && fieldsets.length > 5;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (
        !target.closest("[data-fieldset-selector]") &&
        !target.closest("[data-fieldset-modal]")
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  return (
    <>
      <Container data-fieldset-selector>
        <SelectButton
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          disabled={disabled}
          $hasValue={!!value}
          $isOpen={isOpen}
        >
          <SelectText>{value ? value.name : placeholder}</SelectText>
          <SelectIcon $isOpen={isOpen} />
        </SelectButton>

        <AnimatePresence>
          {isOpen && (
            <DropdownContainer
              initial={{ opacity: 0, scale: 0.95, y: -10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -10 }}
              transition={{ duration: 0.15 }}
            >
              <SearchInputWrapper>
                <SearchIconWrapper>
                  <Search size={14} />
                </SearchIconWrapper>
                <StyledSearchInput
                  type="text"
                  placeholder="Type to search fieldsets..."
                  value={localSearchQuery}
                  onChange={handleSearchChange}
                  autoFocus
                />
                {localSearchQuery && (
                  <ClearButton onClick={handleClearSearch}>
                    <X size={12} />
                  </ClearButton>
                )}
              </SearchInputWrapper>

              <OptionsContainer>
                {loading && !fieldsets.length ? (
                  <LoadingContainer>
                    <Loader2 className="animate-spin" size={18} />
                    <span>Loading fieldsets...</span>
                  </LoadingContainer>
                ) : error ? (
                  <EmptyState>
                    Error loading fieldsets. Please try again.
                  </EmptyState>
                ) : (
                  <>
                    {displayFieldsets.length === 0 ? (
                      <EmptyState>
                        {localSearchQuery
                          ? `No fieldsets found for "${localSearchQuery}"`
                          : "No fieldsets available"}
                      </EmptyState>
                    ) : (
                      <OptionsSection>
                        {!localSearchQuery && (
                          <SectionLabel>Available Fieldsets</SectionLabel>
                        )}
                        {displayFieldsets.map((fieldset) => (
                          <Option
                            key={fieldset.id}
                            onClick={() => handleSelect(fieldset)}
                            whileHover={{ x: 2 }}
                            whileTap={{ scale: 0.98 }}
                          >
                            <Database size={16} />
                            <OptionText>
                              <OptionName>{fieldset.name}</OptionName>
                              {fieldset.description && (
                                <OptionDescription>
                                  {fieldset.description}
                                </OptionDescription>
                              )}
                            </OptionText>
                            <EditButton
                              onClick={(e) => handleEdit(fieldset, e)}
                              whileHover={{ scale: 1.1 }}
                              whileTap={{ scale: 0.9 }}
                            >
                              <Edit3 size={14} />
                            </EditButton>
                          </Option>
                        ))}
                        {hasMore && (
                          <Option
                            onClick={() => setLocalSearchQuery(" ")}
                            style={{
                              justifyContent: "center",
                              color: "#64748b",
                              fontSize: "0.8125rem",
                            }}
                          >
                            Type to search {fieldsets.length - 5} more...
                          </Option>
                        )}
                      </OptionsSection>
                    )}

                    <OptionsSection>
                      <CreateOption
                        onClick={handleCreateNew}
                        whileHover={{ x: 2 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <Plus size={16} />
                        <span>Create New Fieldset</span>
                      </CreateOption>
                    </OptionsSection>
                  </>
                )}
              </OptionsContainer>
            </DropdownContainer>
          )}
        </AnimatePresence>

        {showInfo && value && (
          <InfoBox
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Database />
            <InfoContent>
              <InfoTitle>{value.name}</InfoTitle>
              <InfoDescription>
                {value.description ||
                  `This fieldset contains ${
                    value.columns?.edges?.length || 0
                  } columns for data extraction.`}
              </InfoDescription>
            </InfoContent>
          </InfoBox>
        )}
      </Container>

      <FieldsetModal
        open={showFieldsetModal}
        onClose={() => {
          setShowFieldsetModal(false);
          setEditingFieldset(null);
        }}
        onSuccess={handleFieldsetCreated}
        existingFieldset={editingFieldset}
        data-fieldset-modal
      />
    </>
  );
};
