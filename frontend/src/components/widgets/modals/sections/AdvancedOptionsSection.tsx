import React from "react";
import { Grid, Icon, Popup } from "semantic-ui-react";
import {
  FormSection,
  StyledFormField,
  StyledTextArea,
  StyledInput,
  StyledCheckbox,
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
      <Grid>
        <Grid.Row>
          <Grid.Column width={16}>
            <StyledFormField>
              <label>Parser Instructions</label>
              <StyledTextArea
                rows={3}
                name="instructions"
                placeholder="Provide detailed instructions for extracting object properties here..."
                value={instructions}
                onChange={(
                  e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
                  data: any
                ) => handleChange(e, data, "instructions")}
              />
            </StyledFormField>
          </Grid.Column>
        </Grid.Row>
        <Grid.Row>
          <Grid.Column width={16}>
            <StyledFormField>
              <label>
                Limit Search to Label
                <Popup
                  trigger={<Icon name="question circle outline" />}
                  content="Specify a label name to limit the search scope"
                />
              </label>
              <StyledInput
                placeholder="Enter label name"
                name="limitToLabel"
                value={limitToLabel}
                onChange={(
                  e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
                  data: any
                ) => handleChange(e, data, "limitToLabel")}
                fluid
              />
            </StyledFormField>
          </Grid.Column>
        </Grid.Row>
      </Grid>
    </FormSection>
  );
};
