import styled from "styled-components";

export const FormSection = styled.div`
  margin-bottom: 2rem;
  width: 100%;

  &:last-child {
    margin-bottom: 0;
  }
`;

export const SectionTitle = styled.h3`
  font-size: 1.1rem;
  margin-bottom: 1rem;
  color: #2c3e50;
  border-bottom: 1px solid #eee;
  padding-bottom: 0.5rem;
`;

export const StyledFormField = styled.div`
  margin-bottom: 1rem;

  label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
    color: #34495e;
  }
`;

export const StyledInput = styled.input`
  width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  font-size: 0.9rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;

  &:focus {
    outline: none;
    border-color: #2185d0;
    box-shadow: 0 0 0 1px #2185d0;
  }
`;

export const TaskSelectorWrapper = styled.div`
  .ui.dropdown {
    max-width: 100%;
    word-wrap: break-word;
    white-space: normal;

    .text {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
    }

    .menu > .item {
      word-wrap: break-word;
      white-space: normal;
      padding: 0.5rem 1rem !important;
    }
  }
`;

export const StyledCheckbox = styled.div`
  margin-bottom: 1rem;

  label {
    font-weight: normal;
  }
`;

export const StyledTextArea = styled.textarea`
  min-height: 100px;
  width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  font-size: 0.9rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  resize: vertical;

  &:focus {
    outline: none;
    border-color: #2185d0;
    box-shadow: 0 0 0 1px #2185d0;
  }
`;
