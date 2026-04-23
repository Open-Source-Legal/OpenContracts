import React, { useState, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import { motion } from "framer-motion";
import { X, Check, HelpCircle } from "lucide-react";
import { Button, Dropdown } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { ColumnType } from "../../../types/graphql-api";
import { LooseObject } from "../../types";
import { ExtractTaskDropdown } from "../selectors/ExtractTaskDropdown";
import { FieldType, ModelFieldBuilder } from "../ModelFieldBuilder";
import { parsePydanticModel } from "../../../utils/parseOutputType";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRIMITIVE_TYPE_OPTIONS = [
  { value: "str", label: "String" },
  { value: "int", label: "Integer" },
  { value: "float", label: "Float" },
  { value: "bool", label: "Boolean" },
];

export const DEFAULT_EXTRACT_TASK_NAME =
  "opencontractserver.tasks.data_extract_tasks.doc_extract_query_task";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const generateOutputType = (
  option: string,
  primitive: string,
  fields: FieldType[]
): string => {
  if (option === "primitive") return primitive;
  const fieldLines = fields
    .map((f) => `    ${f.fieldName}: ${f.fieldType}`)
    .join("\n");
  return `class CustomModel(BaseModel):\n${fieldLines}`;
};

// ---------------------------------------------------------------------------
// Styled components
// ---------------------------------------------------------------------------

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
  max-width: 900px;
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
  padding: 2rem 2.5rem;
  background: white;

  @media (max-width: 768px) {
    padding: 1.5rem;
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

const SectionDivider = styled.h3`
  font-size: 0.8125rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const FormRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const FormGroup = styled.div`
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

const StyledInput = styled.input`
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 0.9375rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: ${OS_LEGAL_COLORS.textPrimary};
  box-sizing: border-box;

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

const StyledTextArea = styled.textarea`
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 0.9375rem;
  border: 1.5px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  transition: all 0.2s ease;
  background: #ffffff;
  color: ${OS_LEGAL_COLORS.textPrimary};
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;

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

const RadioGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 1.25rem;
`;

const RadioLabel = styled.label`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;

  input[type="radio"] {
    width: 18px;
    height: 18px;
    accent-color: ${OS_LEGAL_COLORS.primaryBlue};
    cursor: pointer;
  }
`;

const CheckboxLabel = styled.label`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;

  input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: ${OS_LEGAL_COLORS.primaryBlue};
    cursor: pointer;
  }
`;

const Tooltip = styled.span`
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: help;
  color: ${OS_LEGAL_COLORS.textMuted};

  &:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: ${OS_LEGAL_COLORS.textPrimary};
    color: white;
    padding: 0.5rem 0.75rem;
    border-radius: 8px;
    font-size: 0.8125rem;
    font-weight: 400;
    white-space: normal;
    max-width: 280px;
    z-index: 10;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    pointer-events: none;
  }
`;

const SectionSpacer = styled.div`
  margin-top: 2rem;
`;

// ---------------------------------------------------------------------------
// Component interface
// ---------------------------------------------------------------------------

interface CreateColumnModalProps {
  open: boolean;
  existing_column?: ColumnType | null;
  onClose: () => void;
  onSubmit: (data: any) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CreateColumnModal: React.FC<CreateColumnModalProps> = ({
  open,
  existing_column,
  onClose,
  onSubmit,
}) => {
  const [isMounted, setIsMounted] = useState(false);
  const [formData, setFormData] = useState<LooseObject>(
    existing_column ? { ...existing_column } : {}
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [outputTypeOption, setOutputTypeOption] = useState<string>("primitive");
  const [primitiveType, setPrimitiveType] = useState<string>("str");
  const [extractIsList, setExtractIsList] = useState<boolean>(false);
  const [initialFields, setInitialFields] = useState<FieldType[]>([]);

  // Delay mount slightly so parent modal can settle
  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => setIsMounted(true), 50);
      return () => clearTimeout(timer);
    } else {
      setIsMounted(false);
    }
  }, [open]);

  // Initialize form from existing_column or reset for new
  useEffect(() => {
    if (open) {
      if (existing_column) {
        setFormData({ ...existing_column });
        const isPrimitiveType = ["str", "int", "float", "bool"].includes(
          existing_column.outputType || ""
        );
        setOutputTypeOption(isPrimitiveType ? "primitive" : "custom");
        setPrimitiveType(existing_column.outputType);
        setExtractIsList(Boolean(existing_column.extractIsList));
        setInitialFields(parsePydanticModel(existing_column.outputType));
      } else {
        setFormData({
          name: "",
          query: "",
          matchText: "",
          outputType: "str",
          limitToLabel: "",
          instructions: "",
          mustContainText: "",
          taskName: DEFAULT_EXTRACT_TASK_NAME,
        });
        setOutputTypeOption("primitive");
        setPrimitiveType("str");
        setExtractIsList(false);
        setInitialFields([]);
      }
    }
  }, [open, existing_column]);

  // Sync outputType when primitiveType or option changes
  useEffect(() => {
    if (outputTypeOption === "primitive") {
      setFormData((prev) => ({
        ...prev,
        outputType: generateOutputType(outputTypeOption, primitiveType, []),
      }));
    }
  }, [primitiveType, outputTypeOption]);

  const handleFieldChange = useCallback((field: string, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleOutputTypeOptionChange = useCallback(
    (value: string) => {
      setOutputTypeOption(value);
      setFormData((prev) => ({
        ...prev,
        outputType: value === "primitive" ? primitiveType : "",
      }));
    },
    [primitiveType]
  );

  const handlePrimitiveTypeChange = useCallback((value: string) => {
    setPrimitiveType(value);
    setFormData((prev) => ({ ...prev, outputType: value }));
  }, []);

  const handleExtractIsListChange = useCallback((checked: boolean) => {
    setExtractIsList(checked);
    setFormData((prev) => ({ ...prev, extractIsList: checked }));
  }, []);

  const handleFieldsChange = useCallback(
    (fields: FieldType[]) => {
      setFormData((prev) => ({
        ...prev,
        fields,
        outputType: generateOutputType(outputTypeOption, primitiveType, fields),
      }));
    },
    [outputTypeOption, primitiveType]
  );

  const isFormValid = useCallback((): boolean => {
    const name = formData.name || "";
    const query = formData.query || "";
    const taskName = formData.taskName || "";
    return Boolean(name) && Boolean(query) && Boolean(taskName);
  }, [formData]);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      const finalFormData = {
        ...formData,
        outputType:
          outputTypeOption === "primitive"
            ? primitiveType
            : formData.outputType,
      };
      await onSubmit(finalFormData);
      handleClose();
    } catch (error) {
      console.error("Error submitting form:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!existing_column) {
      setFormData({
        name: "",
        query: "",
        matchText: "",
        outputType: "str",
        limitToLabel: "",
        instructions: "",
        mustContainText: "",
        taskName: DEFAULT_EXTRACT_TASK_NAME,
      });
      setOutputTypeOption("primitive");
      setPrimitiveType("str");
      setExtractIsList(false);
      setInitialFields([]);
    }
    onClose();
  };

  if (!open || !isMounted) return null;

  return createPortal(
    <ModalOverlay onClick={handleClose}>
      <ModalContainer
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ─────────────────────────────────────────────── */}
        <ModalHeader>
          <ModalTitle>
            {existing_column ? "Edit Column" : "Create New Column"}
          </ModalTitle>
          <ModalSubtitle>
            Configure an extraction column to pull structured data from your
            documents
          </ModalSubtitle>
          <CloseButton
            onClick={handleClose}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <X />
          </CloseButton>
        </ModalHeader>

        {/* ── Body ───────────────────────────────────────────────── */}
        <ModalBody>
          {/* Section: Basic Configuration */}
          <SectionDivider>Basic Configuration</SectionDivider>
          <FormRow>
            <FormGroup>
              <Label>
                Name <span className="required">*</span>
              </Label>
              <StyledInput
                type="text"
                placeholder="Enter column name"
                value={formData.name || ""}
                onChange={(e) => handleFieldChange("name", e.target.value)}
                disabled={isSubmitting}
                autoFocus
              />
            </FormGroup>
            <FormGroup>
              <Label>Extract Task</Label>
              <ExtractTaskDropdown
                onChange={(taskName: string | null) => {
                  if (taskName) {
                    handleFieldChange("taskName", taskName);
                  }
                }}
                taskName={formData.taskName || ""}
              />
            </FormGroup>
          </FormRow>

          {/* Section: Output Type */}
          <SectionSpacer>
            <SectionDivider>Output Type</SectionDivider>
          </SectionSpacer>
          <FormRow>
            <FormGroup>
              <Label>Select Type</Label>
              <RadioGroup>
                <RadioLabel>
                  <input
                    type="radio"
                    name="outputTypeOption"
                    value="primitive"
                    checked={outputTypeOption === "primitive"}
                    onChange={() => handleOutputTypeOptionChange("primitive")}
                  />
                  Primitive Type
                </RadioLabel>
                <RadioLabel>
                  <input
                    type="radio"
                    name="outputTypeOption"
                    value="custom"
                    checked={outputTypeOption === "custom"}
                    onChange={() => handleOutputTypeOptionChange("custom")}
                  />
                  Custom Model
                </RadioLabel>
              </RadioGroup>
            </FormGroup>
            <FormGroup>
              <Label>&nbsp;</Label>
              <CheckboxLabel>
                <input
                  type="checkbox"
                  checked={extractIsList}
                  onChange={(e) => handleExtractIsListChange(e.target.checked)}
                />
                List of Values
              </CheckboxLabel>
            </FormGroup>
          </FormRow>

          {outputTypeOption === "primitive" && (
            <FormGroup style={{ marginTop: "1rem", maxWidth: "50%" }}>
              <Label>Primitive Type</Label>
              <Dropdown
                mode="select"
                fluid
                options={PRIMITIVE_TYPE_OPTIONS}
                value={primitiveType}
                placeholder="Select primitive type"
                onChange={(value) => handlePrimitiveTypeChange(value as string)}
                clearable={false}
              />
            </FormGroup>
          )}

          {outputTypeOption === "custom" && (
            <div style={{ marginTop: "1rem" }}>
              <ModelFieldBuilder
                onFieldsChange={handleFieldsChange}
                initialFields={initialFields}
              />
            </div>
          )}

          {/* Section: Extraction Configuration */}
          <SectionSpacer>
            <SectionDivider>Extraction Configuration</SectionDivider>
          </SectionSpacer>
          <FormGroup>
            <Label>
              Query <span className="required">*</span>
            </Label>
            <StyledTextArea
              rows={3}
              placeholder="What query shall we use to guide the LLM extraction?"
              value={formData.query || ""}
              onChange={(e) => handleFieldChange("query", e.target.value)}
              disabled={isSubmitting}
            />
          </FormGroup>
          <FormRow style={{ marginTop: "1rem" }}>
            <FormGroup>
              <Label>Must Contain Text</Label>
              <StyledTextArea
                rows={3}
                placeholder="Only look in annotations that contain this string (case insensitive)"
                value={formData.mustContainText || ""}
                onChange={(e) =>
                  handleFieldChange("mustContainText", e.target.value)
                }
                disabled={isSubmitting}
              />
            </FormGroup>
            <FormGroup>
              <Label>
                Representative Example{" "}
                <Tooltip data-tooltip="Find text that is semantically similar to this example FIRST if provided.">
                  <HelpCircle size={14} />
                </Tooltip>
              </Label>
              <StyledTextArea
                rows={3}
                placeholder="Place example of text containing relevant data here"
                value={formData.matchText || ""}
                onChange={(e) => handleFieldChange("matchText", e.target.value)}
                disabled={isSubmitting}
              />
            </FormGroup>
          </FormRow>

          {/* Section: Advanced Options */}
          <SectionSpacer>
            <SectionDivider>Advanced Options</SectionDivider>
          </SectionSpacer>
          <FormRow>
            <FormGroup>
              <Label>Parser Instructions</Label>
              <StyledTextArea
                rows={3}
                placeholder="Provide detailed instructions for extracting object properties here..."
                value={formData.instructions || ""}
                onChange={(e) =>
                  handleFieldChange("instructions", e.target.value)
                }
                disabled={isSubmitting}
              />
            </FormGroup>
            <FormGroup>
              <Label>
                Limit Search to Label{" "}
                <Tooltip data-tooltip="Specify a label name to limit the search scope">
                  <HelpCircle size={14} />
                </Tooltip>
              </Label>
              <StyledInput
                type="text"
                placeholder="Enter label name"
                value={formData.limitToLabel || ""}
                onChange={(e) =>
                  handleFieldChange("limitToLabel", e.target.value)
                }
                disabled={isSubmitting}
              />
            </FormGroup>
          </FormRow>
        </ModalBody>

        {/* ── Footer ─────────────────────────────────────────────── */}
        <ModalFooter>
          <FooterInfo>
            {existing_column
              ? "Editing existing column definition"
              : "All required fields must be filled before submitting"}
          </FooterInfo>
          <ButtonGroup>
            <Button
              variant="secondary"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={isSubmitting}
              disabled={isSubmitting || !isFormValid()}
              leftIcon={<Check size={16} />}
            >
              {existing_column ? "Save Changes" : "Create Column"}
            </Button>
          </ButtonGroup>
        </ModalFooter>
      </ModalContainer>
    </ModalOverlay>,
    document.body
  );
};
