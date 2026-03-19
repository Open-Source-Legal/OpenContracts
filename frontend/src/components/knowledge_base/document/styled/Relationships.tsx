import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export const RelationshipPanel = styled.div`
  padding: 1.5rem;
  height: 100%;
  overflow-y: auto;

  h3 {
    font-size: 1.25rem;
    font-weight: 500;
    color: #212529;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
`;

export const RelationshipCard = styled.div`
  width: 100%;
  margin-bottom: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
  border: 1px solid rgba(231, 234, 237, 0.7);
  border-radius: 8px;
  background: white;
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }

  .content {
    padding: 1.25rem;
  }
`;

export const RelationshipType = styled.div`
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  background: rgba(33, 133, 208, 0.1);
  padding: 0.25rem 0.75rem;
  border-radius: 1rem;
  margin-bottom: 0.75rem;
`;
