import React from "react";
import { Popup } from "semantic-ui-react";
import { HelpCircle } from "lucide-react";
import { VStack } from "@os-legal/ui";
import { FormSection, StyledFormField, StyledTextArea } from "../styled";
import { SectionTitle } from "../styled";

interface ExtractionConfigSectionProps {
  query: string;
  mustContainText: string;
  matchText: string;
  handleChange: (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    data: any,
    fieldName: string
  ) => void;
}

export const ExtractionConfigSection: React.FC<
  ExtractionConfigSectionProps
> = ({ query, mustContainText, matchText, handleChange }) => {
  return (
    <FormSection>
      <SectionTitle>Extraction Configuration</SectionTitle>
      <VStack gap="md">
        <StyledFormField>
          <label>Query</label>
          <StyledTextArea
            rows={3}
            name="query"
            placeholder="What query shall we use to guide the LLM extraction?"
            value={query}
            onChange={(e) =>
              handleChange(e, { value: e.target.value }, "query")
            }
          />
        </StyledFormField>
        <StyledFormField>
          <label>Must Contain Text</label>
          <StyledTextArea
            rows={3}
            name="mustContainText"
            placeholder="Only look in annotations that contain this string (case insensitive)?"
            value={mustContainText}
            onChange={(e) =>
              handleChange(e, { value: e.target.value }, "mustContainText")
            }
          />
        </StyledFormField>
        <StyledFormField>
          <label>
            Representative Example
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
              content="Find text that is semantically similar to this example FIRST if provided."
            />
          </label>
          <StyledTextArea
            rows={3}
            name="matchText"
            placeholder="Place example of text containing relevant data here."
            value={matchText}
            onChange={(e) =>
              handleChange(e, { value: e.target.value }, "matchText")
            }
          />
        </StyledFormField>
      </VStack>
    </FormSection>
  );
};
