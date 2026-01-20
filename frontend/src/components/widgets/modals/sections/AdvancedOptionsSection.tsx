import React from "react";
import { Popup } from "semantic-ui-react";
import { HelpCircle } from "lucide-react";
import { VStack } from "@os-legal/ui";
import {
  FormSection,
  StyledFormField,
  StyledTextArea,
  StyledInput,
} from "../styled";
import { SectionTitle } from "../styled";

interface AdvancedOptionsSectionProps {
  instructions: string;
  limitToLabel: string;
  handleChange: (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    data: any,
    fieldName: string
  ) => void;
}

export const AdvancedOptionsSection: React.FC<AdvancedOptionsSectionProps> = ({
  instructions,
  limitToLabel,
  handleChange,
}) => {
  return (
    <FormSection>
      <SectionTitle>Advanced Options</SectionTitle>
      <VStack gap="md">
        <StyledFormField>
          <label>Parser Instructions</label>
          <StyledTextArea
            rows={3}
            name="instructions"
            placeholder="Provide detailed instructions for extracting object properties here..."
            value={instructions}
            onChange={(e) =>
              handleChange(e, { value: e.target.value }, "instructions")
            }
          />
        </StyledFormField>
        <StyledFormField>
          <label>
            Limit Search to Label
            <Popup
              trigger={
                <HelpCircle
                  size={14}
                  style={{
                    marginLeft: "0.25rem",
                    verticalAlign: "middle",
                    cursor: "pointer",
                  }}
                />
              }
              content="Specify a label name to limit the search scope"
            />
          </label>
          <StyledInput
            placeholder="Enter label name"
            name="limitToLabel"
            value={limitToLabel}
            onChange={(e) =>
              handleChange(e, { value: e.target.value }, "limitToLabel")
            }
          />
        </StyledFormField>
      </VStack>
    </FormSection>
  );
};
