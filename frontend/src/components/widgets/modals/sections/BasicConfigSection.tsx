import React from "react";
import { HStack } from "@os-legal/ui";
import { ExtractTaskDropdown } from "../../selectors/ExtractTaskDropdown";
import {
  FormSection,
  SectionTitle,
  StyledFormField,
  StyledInput,
  TaskSelectorWrapper,
} from "../styled";

interface BasicConfigSectionProps {
  name: string;
  taskName: string;
  handleChange: (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    data: any,
    fieldName: string
  ) => void;
  setFormData: (
    updater: (prev: Record<string, any>) => Record<string, any>
  ) => void;
}

export const BasicConfigSection: React.FC<BasicConfigSectionProps> = ({
  name,
  taskName,
  handleChange,
  setFormData,
}) => {
  return (
    <FormSection>
      <SectionTitle>Basic Configuration</SectionTitle>
      <HStack gap="md" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <StyledFormField>
            <label>Name</label>
            <StyledInput
              placeholder="Enter column name"
              name="name"
              value={name}
              onChange={(e) =>
                handleChange(e, { value: e.target.value }, "name")
              }
            />
          </StyledFormField>
        </div>
        <div style={{ flex: 1 }}>
          <StyledFormField>
            <label>Extract Task</label>
            <TaskSelectorWrapper>
              <ExtractTaskDropdown
                onChange={(taskName: string | null) => {
                  if (taskName) {
                    setFormData((prev) => ({ ...prev, taskName }));
                  }
                }}
                taskName={taskName}
              />
            </TaskSelectorWrapper>
          </StyledFormField>
        </div>
      </HStack>
    </FormSection>
  );
};
