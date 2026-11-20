import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { LoadingOverlay } from "../../common/LoadingOverlay";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

import { useReactiveVar, useQuery, useMutation } from "@apollo/client";
import { selectedCorpus, selectedFieldset } from "../../../graphql/cache";
import {
  REQUEST_GET_EXTRACT,
  RequestGetExtractInput,
  RequestGetExtractOutput,
  GET_EXTRACTS,
  GetExtractsOutput,
} from "../../../graphql/queries";
import { CorpusDropdown } from "../selectors/CorpusDropdown";
import { UnifiedFieldsetSelector } from "../selectors/UnifiedFieldsetSelector";
import { FieldsetType } from "../../../types/graphql-api";
import {
  REQUEST_CREATE_EXTRACT,
  RequestCreateExtractInputType,
  RequestCreateExtractOutputType,
} from "../../../graphql/mutations";
import { toast } from "react-toastify";

// Uses createPortal to render at document.body, bypassing ancestor
// overflow:hidden containers that would clip position:fixed content.
// TODO: Migrate to @os-legal/ui Modal when available — currently uses custom
// ModalOverlay/ModalContainer for framer-motion animation support
const ModalOverlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
`;

const ModalContainer = styled(motion.div)`
  background: white;
  border-radius: 16px;
  box-shadow:
    0 20px 25px -5px rgba(0, 0, 0, 0.1),
    0 10px 10px -5px rgba(0, 0, 0, 0.04);
  width: 100%;
  max-width: 720px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;

  @media (max-width: 768px) {
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
  }
`;

const ModalHeader = styled.div`
  padding: 2rem 2.5rem 1.75rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  position: relative;
  background: linear-gradient(
    to bottom,
    #fbfcfd 0%,
    ${OS_LEGAL_COLORS.gray50} 100%
  );
`;

const ModalTitle = styled.h2`
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  letter-spacing: -0.025em;
`;

const ModalSubtitle = styled.p`
  margin: 0.625rem 0 0;
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.5;
  max-width: 85%;
`;

const CloseButton = styled(motion.button)`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: none;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

  svg {
    width: 20px;
    height: 20px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);

    svg {
      color: ${OS_LEGAL_COLORS.textTertiary};
    }
  }
`;

const ModalBody = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 2rem 2.5rem 2.5rem;
  background: white;

  @media (max-width: 768px) {
    padding: 1.5rem;
  }
`;

const StyledForm = styled.form`
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
`;

const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
`;

const Label = styled.label`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: flex;
  align-items: center;
  gap: 0.25rem;
  letter-spacing: 0.025em;

  .required {
    color: ${OS_LEGAL_COLORS.danger};
    font-weight: 400;
  }
`;

const InputWrapper = styled.div`
  position: relative;
  width: 100%;
`;

const StyledInput = styled.input`
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 0.9375rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: ${OS_LEGAL_COLORS.textPrimary};

  &:hover:not(:focus) {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
    background: #ffffff;
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }

  &:disabled {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    cursor: not-allowed;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const HelperText = styled.p`
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.5;

  strong {
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

const DropdownWrapper = styled.div`
  .ui.dropdown {
    width: 100% !important;
    min-height: auto !important;

    &.selection {
      padding: 0.75rem 1rem !important;
      font-size: 0.9375rem !important;
      border: 1.5px solid ${OS_LEGAL_COLORS.border} !important;
      border-radius: 10px !important;
      background: white !important;
      transition: all 0.2s ease !important;
      min-height: 44px !important;

      &:hover:not(.active) {
        border-color: ${OS_LEGAL_COLORS.borderHover} !important;
        background: ${OS_LEGAL_COLORS.surfaceHover} !important;
      }

      &.active,
      &.visible {
        border-color: ${OS_LEGAL_COLORS.primaryBlue} !important;
        box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12) !important;
        background: white !important;
      }

      .text {
        color: ${OS_LEGAL_COLORS.textPrimary} !important;
        font-weight: 500 !important;
      }

      .default.text {
        color: ${OS_LEGAL_COLORS.textMuted} !important;
        font-weight: 400 !important;
      }

      i.dropdown.icon {
        color: ${OS_LEGAL_COLORS.textSecondary} !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        font-size: 1.25rem !important;
      }
    }

    .menu {
      border: 1.5px solid ${OS_LEGAL_COLORS.border} !important;
      border-radius: 10px !important;
      margin-top: 0.375rem !important;
      box-shadow:
        0 10px 15px -3px rgba(0, 0, 0, 0.1),
        0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;

      .item {
        padding: 0.625rem 1rem !important;
        font-size: 0.9375rem !important;
        color: ${OS_LEGAL_COLORS.textPrimary} !important;

        &:hover {
          background: ${OS_LEGAL_COLORS.surfaceLight} !important;
          color: ${OS_LEGAL_COLORS.textPrimary} !important;
        }

        &.selected {
          background: ${OS_LEGAL_COLORS.blueSurface} !important;
          color: ${OS_LEGAL_COLORS.primaryBlueHover} !important;
          font-weight: 500 !important;
        }
      }
    }
  }
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2.5rem 1.75rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: linear-gradient(
    to top,
    #fbfcfd 0%,
    ${OS_LEGAL_COLORS.gray50} 100%
  );
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;

  @media (max-width: 640px) {
    flex-direction: column-reverse;
    padding: 1.25rem 1.5rem;
  }
`;

const FooterInfo = styled.div`
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  gap: 0.5rem;

  @media (max-width: 640px) {
    text-align: center;
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 0.75rem;

  @media (max-width: 640px) {
    width: 100%;
    flex-direction: column-reverse;
  }
`;

const StyledButton = styled(motion.button)<{
  $variant?: "primary" | "secondary";
}>`
  padding: 0.625rem 1.25rem;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-width: 100px;
  height: 40px;

  ${(props) =>
    props.$variant === "primary"
      ? `
    background: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;
    border: 1.5px solid ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.primaryBlueHover};
      border-color: ${OS_LEGAL_COLORS.primaryBlueHover};
      box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.1);
      transform: translateY(-0.5px);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
      box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }

    &:disabled {
      background: ${OS_LEGAL_COLORS.textMuted};
      border-color: ${OS_LEGAL_COLORS.textMuted};
      cursor: not-allowed;
      opacity: 1;
    }
  `
      : `
    background: white;
    color: ${OS_LEGAL_COLORS.textTertiary};
    border: 1.5px solid ${OS_LEGAL_COLORS.border};

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.surfaceHover};
      border-color: ${OS_LEGAL_COLORS.borderHover};
      color: ${OS_LEGAL_COLORS.textTertiary};
    }

    &:active:not(:disabled) {
      background: ${OS_LEGAL_COLORS.surfaceLight};
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  `}

  @media (max-width: 640px) {
    width: 100%;
    padding: 0.875rem 1.5rem;
    height: 48px;
  }
`;

const LoadingSpinner = styled(motion.div)`
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
`;

// Main component
interface ExtractModalProps {
  open: boolean;
  onClose: () => void;
  extractId?: string;
  fieldsetId?: string;
  corpusId?: string;
}

export const CreateExtractModal: React.FC<ExtractModalProps> = ({
  open,
  onClose,
  extractId,
  fieldsetId,
  corpusId,
}) => {
  const [name, setName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [localSelectedFieldset, setLocalSelectedFieldset] =
    useState<FieldsetType | null>(null);
  const selected_corpus = useReactiveVar(selectedCorpus);
  const selected_fieldset = useReactiveVar(selectedFieldset);

  const { loading, error, data } = useQuery<
    RequestGetExtractOutput,
    RequestGetExtractInput
  >(REQUEST_GET_EXTRACT, {
    variables: { id: extractId || "" },
    skip: !extractId,
  });

  const [createExtract, { loading: createExtractLoading }] = useMutation<
    RequestCreateExtractOutputType,
    RequestCreateExtractInputType
  >(REQUEST_CREATE_EXTRACT, {
    update(cache, { data: mutationData }) {
      if (!mutationData?.createExtract.ok || !mutationData.createExtract.obj)
        return;

      const newExtract = mutationData.createExtract.obj;
      const effectiveCorpusId = corpusId ?? selected_corpus?.id;

      // Build the list of cache queries to update (corpus-specific + global)
      const queriesToUpdate: Record<string, any>[] = [{ searchText: "" }, {}];
      if (effectiveCorpusId) {
        queriesToUpdate.push({
          corpusId: effectiveCorpusId,
          corpusAction_Isnull: true,
        });
        queriesToUpdate.push({ corpusId: effectiveCorpusId });
      }

      for (const variables of queriesToUpdate) {
        try {
          const existing = cache.readQuery<GetExtractsOutput>({
            query: GET_EXTRACTS,
            variables,
          });
          if (existing) {
            cache.writeQuery({
              query: GET_EXTRACTS,
              variables,
              data: {
                extracts: {
                  ...existing.extracts,
                  edges: [
                    { __typename: "ExtractTypeEdge", node: newExtract },
                    ...existing.extracts.edges,
                  ],
                },
              },
            });
          }
        } catch {
          // Cache miss for this variable combo — skip
        }
      }
    },
  });

  useEffect(() => {
    if (data?.extract) {
      setName(data.extract.name);
    }
  }, [data]);

  useEffect(() => {
    if (selected_fieldset) {
      setLocalSelectedFieldset(selected_fieldset);
    }
  }, [selected_fieldset]);

  const handleFieldsetChange = (fieldset: FieldsetType | null) => {
    setLocalSelectedFieldset(fieldset);
    selectedFieldset(fieldset);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!extractId && name.trim()) {
      try {
        setIsSubmitting(true);
        const effectiveCorpusId = corpusId ?? selected_corpus?.id;
        const { data } = await createExtract({
          variables: {
            ...(effectiveCorpusId ? { corpusId: effectiveCorpusId } : {}),
            ...(localSelectedFieldset?.id
              ? { fieldsetId: localSelectedFieldset?.id }
              : {}),
            name,
          },
        });
        if (data?.createExtract.ok) {
          selectedCorpus(null);
          selectedFieldset(null);
          toast.success("Extract created successfully!");
          onClose();
        } else {
          toast.error(`Failed to create extract: ${data?.createExtract.msg}`);
        }
      } catch (error) {
        console.error("Error creating extract:", error);
        toast.error("An error occurred while creating the extract");
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const handleClose = () => {
    setName("");
    setLocalSelectedFieldset(null);
    selectedCorpus(null);
    selectedFieldset(null);
    onClose();
  };

  if (loading) return null;
  if (error) return null;
  if (!open) return null;

  const isLoading = isSubmitting || createExtractLoading;

  return createPortal(
    <ModalOverlay onClick={handleClose}>
      <ModalContainer
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
      >
        <ModalHeader>
          <ModalTitle>
            {extractId ? "Edit Extract" : "Create New Extract"}
          </ModalTitle>
          <ModalSubtitle>
            Set up a new data extraction workflow to analyze your documents
          </ModalSubtitle>
          <CloseButton
            onClick={handleClose}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <X />
          </CloseButton>
        </ModalHeader>

        <ModalBody>
          <StyledForm onSubmit={handleSubmit}>
            <FormSection>
              <Label>
                Extract Name <span className="required">*</span>
              </Label>
              <InputWrapper>
                <StyledInput
                  type="text"
                  placeholder="Enter a descriptive name for your extract"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={isLoading}
                  autoFocus
                />
              </InputWrapper>
              <HelperText>
                Choose a clear, descriptive name that helps identify this
                extract's purpose
              </HelperText>
            </FormSection>

            {!corpusId && (
              <FormSection>
                <Label>Select Corpus</Label>
                <DropdownWrapper>
                  <CorpusDropdown
                    placeholder="Choose a corpus to load documents from"
                    fluid
                  />
                </DropdownWrapper>
                <HelperText>
                  <strong>Optional:</strong> Select a corpus to automatically
                  load all its documents into this extract
                </HelperText>
              </FormSection>
            )}

            {!fieldsetId && (
              <FormSection>
                <Label>Select Fieldset</Label>
                <UnifiedFieldsetSelector
                  value={localSelectedFieldset}
                  onChange={handleFieldsetChange}
                  placeholder="Search or create a fieldset..."
                  disabled={isLoading}
                />
                <HelperText>
                  <strong>Optional:</strong> Choose a predefined set of columns,
                  or create them later in the extract editor
                </HelperText>
              </FormSection>
            )}
          </StyledForm>
        </ModalBody>

        <ModalFooter>
          <FooterInfo>
            {localSelectedFieldset
              ? `Using ${
                  localSelectedFieldset.columns?.edges?.length || 0
                } predefined columns`
              : "You can add columns after creating the extract"}
          </FooterInfo>
          <ButtonGroup>
            <StyledButton
              type="button"
              onClick={handleClose}
              disabled={isLoading}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              Cancel
            </StyledButton>
            <StyledButton
              $variant="primary"
              onClick={handleSubmit}
              disabled={isLoading || !name.trim()}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {isLoading ? (
                <>
                  <LoadingSpinner
                    animate={{ rotate: 360 }}
                    transition={{
                      duration: 1,
                      repeat: Infinity,
                      ease: "linear",
                    }}
                  />
                  Creating...
                </>
              ) : (
                "Create Extract"
              )}
            </StyledButton>
          </ButtonGroup>
        </ModalFooter>

        <LoadingOverlay
          active={isLoading}
          inverted
          content="Creating your extract..."
        />
      </ModalContainer>
    </ModalOverlay>,
    document.body
  );
};
