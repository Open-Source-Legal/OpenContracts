import React from "react";
import { Dropdown } from "semantic-ui-react";
import { VStack, Radio, RadioGroup, Checkbox, FormField } from "@os-legal/ui";
import { FormSection, SectionTitle } from "../styled";
import { FieldType, ModelFieldBuilder } from "../../ModelFieldBuilder";

interface OutputTypeSectionProps {
  outputTypeOption: string;
  extractIsList: boolean;
  primitiveType: string;
  handleOutputTypeChange: (
    e: React.FormEvent<HTMLInputElement>,
    data: any
  ) => void;
  handlePrimitiveTypeChange: (value: string) => void;
  handleChange: (
    e: React.SyntheticEvent<HTMLElement>,
    data: any,
    fieldName: string
  ) => void;
  setFormData: (
    updater: (prev: Record<string, any>) => Record<string, any>
  ) => void;
  initialFields?: FieldType[];
}

/**
 * Generates the final output type string based on the selected options
 */
const generateOutputType = (
  outputTypeOption: string,
  primitiveType: string,
  fields: any[]
): string => {
  if (outputTypeOption === "primitive") {
    return primitiveType;
  }

  // Generate Pydantic model
  const fieldLines = fields
    .map((field) => `    ${field.fieldName}: ${field.fieldType}`)
    .join("\n");
  return `class CustomModel(BaseModel):\n${fieldLines}`;
};

export const OutputTypeSection: React.FC<OutputTypeSectionProps> = ({
  outputTypeOption,
  extractIsList,
  primitiveType,
  handleOutputTypeChange,
  handlePrimitiveTypeChange,
  handleChange,
  setFormData,
  initialFields = [],
}) => {
  const handleFieldsChange = (fields: any[]) => {
    setFormData((prev) => ({
      ...prev,
      fields,
      outputType: generateOutputType(outputTypeOption, primitiveType, fields),
    }));
  };

  // Update output type when primitive type changes
  React.useEffect(() => {
    if (outputTypeOption === "primitive") {
      setFormData((prev) => ({
        ...prev,
        outputType: generateOutputType(outputTypeOption, primitiveType, []),
      }));
    }
  }, [primitiveType, outputTypeOption]);

  return (
    <FormSection>
      <SectionTitle>Output Type Configuration</SectionTitle>
      <VStack gap="md">
        <FormField label="Select Type:">
          <RadioGroup
            orientation="horizontal"
            value={outputTypeOption}
            onChange={(value) => {
              // Create a minimal synthetic event with required properties
              const syntheticEvent = {
                target: { value },
              } as unknown as React.FormEvent<HTMLInputElement>;
              handleOutputTypeChange(syntheticEvent, { value });
            }}
          >
            <Radio label="Primitive Type" value="primitive" />
            <Radio label="Custom Model" value="custom" />
          </RadioGroup>
        </FormField>

        <Checkbox
          label="List of Values"
          checked={extractIsList}
          onChange={(e) => {
            const syntheticData = { checked: e.target.checked };
            handleChange(e as any, syntheticData, "extractIsList");
          }}
        />

        {outputTypeOption === "primitive" && (
          <div style={{ width: "50%" }}>
            <FormField label="Primitive Type">
              <Dropdown
                selection
                fluid
                options={[
                  { key: "str", text: "String", value: "str" },
                  { key: "int", text: "Integer", value: "int" },
                  { key: "float", text: "Float", value: "float" },
                  { key: "bool", text: "Boolean", value: "bool" },
                ]}
                value={primitiveType}
                onChange={(e, data) => {
                  if (data.value) {
                    handlePrimitiveTypeChange(String(data.value));
                  }
                }}
                placeholder="Select primitive type"
              />
            </FormField>
          </div>
        )}

        {outputTypeOption === "custom" && (
          <div style={{ width: "100%" }}>
            <ModelFieldBuilder
              onFieldsChange={handleFieldsChange}
              initialFields={initialFields}
            />
          </div>
        )}
      </VStack>
    </FormSection>
  );
};
