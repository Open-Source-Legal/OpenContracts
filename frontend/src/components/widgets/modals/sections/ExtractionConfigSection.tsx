import React from "react";
import { Grid, Popup } from "semantic-ui-react";
import { HelpCircle } from "lucide-react";
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
      <Grid>
        <Grid.Row>
          <Grid.Column width={16}>
            <StyledFormField>
              <label>Query</label>
              <StyledTextArea
                rows={3}
                name="query"
                placeholder="What query shall we use to guide the LLM extraction?"
                value={query}
                onChange={(
                  e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
                  data: any
                ) => handleChange(e, data, "query")}
              />
            </StyledFormField>
          </Grid.Column>
        </Grid.Row>
        <Grid.Row>
          <Grid.Column width={16}>
            <StyledFormField>
              <label>Must Contain Text</label>
              <StyledTextArea
                rows={3}
                name="mustContainText"
                placeholder="Only look in annotations that contain this string (case insensitive)?"
                value={mustContainText}
                onChange={(
                  e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
                  data: any
                ) => handleChange(e, data, "mustContainText")}
              />
            </StyledFormField>
          </Grid.Column>
        </Grid.Row>
        <Grid.Row>
          <Grid.Column width={16}>
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
                onChange={(
                  e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
                  data: any
                ) => handleChange(e, data, "matchText")}
              />
            </StyledFormField>
          </Grid.Column>
        </Grid.Row>
      </Grid>
    </FormSection>
  );
};
