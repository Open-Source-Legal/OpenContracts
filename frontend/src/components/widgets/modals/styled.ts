import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

export const StyledTextArea = styled.textarea`
  min-height: 100px;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  font-size: 1rem;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;

  &:focus {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 1px ${OS_LEGAL_COLORS.primaryBlue};
  }
`;
