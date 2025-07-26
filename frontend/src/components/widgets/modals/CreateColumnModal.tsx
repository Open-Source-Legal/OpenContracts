import React, { useState, useCallback, useEffect } from "react";
import ReactDOM from "react-dom";
import { Modal, Form, Grid, Button } from "semantic-ui-react";
import { BasicConfigSection } from "./sections/BasicConfigSection";
import { OutputTypeSection } from "./sections/OutputTypeSection";
import { ExtractionConfigSection } from "./sections/ExtractionConfigSection";
import { AdvancedOptionsSection } from "./sections/AdvancedOptionsSection";
import { LooseObject } from "../../types";
import styled from "styled-components";
import { ColumnType } from "../../../types/graphql-api";
import { parsePydanticModel } from "../../../utils/parseOutputType";
import { FieldType } from "../ModelFieldBuilder";

interface CreateColumnModalProps {
  open: boolean;
  existing_column?: ColumnType | null;
  onClose: () => void;
  onSubmit: (data: any) => void;
}

interface RequiredFields {
  query: string;
  primitiveType?: string;
  taskName: string;
  name: string;
}

const StyledGrid = styled(Grid)`
  margin: 0 !important;
`;

const ModalWrapper = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999999999;
`;

const ModalDialog = styled.div`
  background: white;
  border-radius: 8px;
  max-width: 900px;
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
`;

const ModalHeader = styled.div`
  padding: 1.5rem;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 1.25rem;
  font-weight: 600;
`;

const ModalBody = styled.div`
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
`;

const ModalFooter = styled.div`
  padding: 1rem 1.5rem;
  border-top: 1px solid #e0e0e0;
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
`;

const CloseButton = styled.button`
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #666;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    color: #000;
  }
`;

/**
 * Modal component for creating or editing a data extract column.
 *
 * @param open - Whether the modal is open.
 * @param existing_column - An existing column to edit.
 * @param onClose - Function to call when closing the modal.
 * @param onSubmit - Function to call with the data upon form submission.
 */
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

  useEffect(() => {
    if (open) {
      // Small delay to ensure parent modal is settled
      const timer = setTimeout(() => setIsMounted(true), 50);
      return () => clearTimeout(timer);
    } else {
      setIsMounted(false);
    }
  }, [open]);

  useEffect(() => {
    if (open) {
      if (existing_column) {
        // Editing existing column
        setFormData({ ...existing_column });
        const isPrimitiveType = ["str", "int", "float", "bool"].includes(
          existing_column.outputType || ""
        );
        setOutputTypeOption(isPrimitiveType ? "primitive" : "custom");
        setPrimitiveType(existing_column.outputType);
        setExtractIsList(Boolean(existing_column.extractIsList));
        setInitialFields(parsePydanticModel(existing_column.outputType));
      } else {
        // Creating new column - reset everything
        setFormData({
          name: "",
          query: "",
          matchText: "",
          outputType: "str",
          limitToLabel: "",
          instructions: "",
          mustContainText: "",
          taskName:
            "opencontractserver.tasks.data_extract_tasks.doc_extract_query_task", // Default task
        });
        setOutputTypeOption("primitive");
        setPrimitiveType("str");
        setExtractIsList(false);
        setInitialFields([]);
      }
    }
  }, [open, existing_column]);

  const handleChange = useCallback(
    (
      event: React.SyntheticEvent<HTMLElement>,
      data: any,
      fieldName: string
    ) => {
      const value = data.type === "checkbox" ? data.checked : data.value;
      setFormData((prev) => ({ ...prev, [fieldName]: value }));
      if (fieldName === "extractIsList") {
        setExtractIsList(value);
      }
    },
    []
  );

  const handleOutputTypeChange = (
    e: React.FormEvent<HTMLInputElement>,
    data: any
  ) => {
    setOutputTypeOption(data.value);
    setFormData((prev) => ({
      ...prev,
      outputType: data.value === "primitive" ? primitiveType : "",
    }));
  };

  const handlePrimitiveTypeChange = (value: string) => {
    setPrimitiveType(value);
    setFormData((prev) => ({
      ...prev,
      outputType: value,
    }));
  };

  const isFormValid = useCallback((): boolean => {
    const requiredFields: RequiredFields = {
      query: formData.query || "",
      taskName: formData.taskName || "",
      name: formData.name || "",
    };

    return Object.entries(requiredFields).every(([key, value]) => {
      return Boolean(value);
    });
  }, [formData]);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      // Ensure outputType is set correctly based on outputTypeOption
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
    // Reset form state when closing
    if (!existing_column) {
      setFormData({
        name: "",
        query: "",
        matchText: "",
        outputType: "str",
        limitToLabel: "",
        instructions: "",
        mustContainText: "",
        taskName:
          "opencontractserver.tasks.data_extract_tasks.doc_extract_query_task",
      });
      setOutputTypeOption("primitive");
      setPrimitiveType("str");
      setExtractIsList(false);
      setInitialFields([]);
    }
    onClose();
  };

  if (!open || !isMounted) return null;

  return ReactDOM.createPortal(
    <ModalWrapper onClick={handleClose}>
      <ModalDialog onClick={(e) => e.stopPropagation()}>
        <ModalHeader>
          {existing_column ? "Edit Column" : "Create a New Data Extract Column"}
          <CloseButton onClick={handleClose}>&times;</CloseButton>
        </ModalHeader>
        <ModalBody>
          <Form>
            <StyledGrid>
              <BasicConfigSection
                name={formData.name || ""}
                taskName={formData.taskName || ""}
                handleChange={handleChange}
                setFormData={setFormData}
              />
              <OutputTypeSection
                outputTypeOption={outputTypeOption}
                extractIsList={extractIsList}
                primitiveType={primitiveType}
                handleOutputTypeChange={handleOutputTypeChange}
                handlePrimitiveTypeChange={handlePrimitiveTypeChange}
                handleChange={handleChange}
                setFormData={setFormData}
                initialFields={initialFields}
              />
              <ExtractionConfigSection
                query={formData.query || ""}
                mustContainText={formData.mustContainText || ""}
                matchText={formData.matchText || ""}
                handleChange={handleChange}
              />
              <AdvancedOptionsSection
                instructions={formData.instructions || ""}
                limitToLabel={formData.limitToLabel || ""}
                handleChange={handleChange}
              />
            </StyledGrid>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button color="black" onClick={handleClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            content="Submit"
            labelPosition="right"
            icon="checkmark"
            onClick={handleSubmit}
            positive
            loading={isSubmitting}
            disabled={isSubmitting || !isFormValid()}
          />
        </ModalFooter>
      </ModalDialog>
    </ModalWrapper>,
    document.body
  );
};
