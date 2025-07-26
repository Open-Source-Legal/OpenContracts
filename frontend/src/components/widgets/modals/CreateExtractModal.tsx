import React, { useState, useEffect } from "react";
import { Modal, Form, Dimmer, Loader } from "semantic-ui-react";
import styled from "styled-components";
import { motion } from "framer-motion";
import { X } from "lucide-react";

import { useReactiveVar, useQuery, useMutation } from "@apollo/client";
import { selectedCorpus, selectedFieldset } from "../../../graphql/cache";
import {
  REQUEST_GET_EXTRACT,
  RequestGetExtractInput,
  RequestGetExtractOutput,
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

// Modern styled components with professional design
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
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
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
  border-bottom: 1px solid #e5e7eb;
  position: relative;
  background: linear-gradient(to bottom, #fbfcfd 0%, #f9fafb 100%);
`;

const ModalTitle = styled.h2`
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
`;

const ModalSubtitle = styled.p`
  margin: 0.625rem 0 0;
  font-size: 0.9375rem;
  color: #64748b;
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
    color: #6b7280;
  }

  &:hover {
    background: #f3f4f6;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);

    svg {
      color: #374151;
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

const StyledForm = styled(Form)`
  && {
    display: flex;
    flex-direction: column;
    gap: 1.75rem;
  }
`;

const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
`;

const Label = styled.label`
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  letter-spacing: 0.025em;

  .required {
    color: #dc2626;
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
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: #0f172a;

  &:hover:not(:focus) {
    border-color: #cbd5e1;
    background: #fafbfc;
  }

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12);
    background: #ffffff;
  }

  &::placeholder {
    color: #94a3b8;
  }

  &:disabled {
    background: #f8fafc;
    cursor: not-allowed;
    color: #94a3b8;
  }
`;

const HelperText = styled.p`
  margin: 0.25rem 0 0;
  font-size: 0.8125rem;
  color: #64748b;
  line-height: 1.5;

  strong {
    font-weight: 600;
    color: #475569;
  }
`;

const DropdownWrapper = styled.div`
  .ui.dropdown {
    width: 100% !important;
    min-height: auto !important;

    &.selection {
      padding: 0.75rem 1rem !important;
      font-size: 0.9375rem !important;
      border: 1.5px solid #e2e8f0 !important;
      border-radius: 10px !important;
      background: white !important;
      transition: all 0.2s ease !important;
      min-height: 44px !important;

      &:hover:not(.active) {
        border-color: #cbd5e1 !important;
        background: #fafbfc !important;
      }

      &.active,
      &.visible {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 3.5px rgba(59, 130, 246, 0.12) !important;
        background: white !important;
      }

      .text {
        color: #0f172a !important;
        font-weight: 500 !important;
      }

      .default.text {
        color: #94a3b8 !important;
        font-weight: 400 !important;
      }

      i.dropdown.icon {
        color: #64748b !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        font-size: 1.25rem !important;
      }
    }

    .menu {
      border: 1.5px solid #e2e8f0 !important;
      border-radius: 10px !important;
      margin-top: 0.375rem !important;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1),
        0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;

      .item {
        padding: 0.625rem 1rem !important;
        font-size: 0.9375rem !important;
        color: #0f172a !important;

        &:hover {
          background: #f1f5f9 !important;
          color: #0f172a !important;
        }

        &.selected {
          background: #eff6ff !important;
          color: #2563eb !important;
          font-weight: 500 !important;
        }
      }
    }
  }
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2.5rem 1.75rem;
  border-top: 1px solid #e5e7eb;
  background: linear-gradient(to top, #fbfcfd 0%, #f9fafb 100%);
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
  color: #64748b;
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

const Button = styled(motion.button)<{ $variant?: "primary" | "secondary" }>`
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
    background: #3b82f6;
    color: white;
    border: 1.5px solid #3b82f6;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);

    &:hover:not(:disabled) {
      background: #2563eb;
      border-color: #2563eb;
      box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.1);
      transform: translateY(-0.5px);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
      box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }

    &:disabled {
      background: #94a3b8;
      border-color: #94a3b8;
      cursor: not-allowed;
      opacity: 1;
    }
  `
      : `
    background: white;
    color: #475569;
    border: 1.5px solid #e2e8f0;

    &:hover:not(:disabled) {
      background: #f8fafc;
      border-color: #cbd5e1;
      color: #334155;
    }

    &:active:not(:disabled) {
      background: #f1f5f9;
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
  >(REQUEST_CREATE_EXTRACT);

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
        const { data } = await createExtract({
          variables: {
            ...(selected_corpus?.id ? { corpusId: selected_corpus?.id } : {}),
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

  return (
    <Modal
      open={open}
      onClose={handleClose}
      size="large"
      style={{ position: "relative" }}
    >
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
                    <strong>Optional:</strong> Choose a predefined set of
                    columns, or create them later in the extract editor
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
              <Button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                Cancel
              </Button>
              <Button
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
              </Button>
            </ButtonGroup>
          </ModalFooter>

          {isLoading && (
            <Dimmer active inverted style={{ borderRadius: "20px" }}>
              <Loader inverted>Creating your extract...</Loader>
            </Dimmer>
          )}
        </ModalContainer>
      </ModalOverlay>
    </Modal>
  );
};
