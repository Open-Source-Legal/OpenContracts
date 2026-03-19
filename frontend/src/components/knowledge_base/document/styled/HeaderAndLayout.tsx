import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export const HeaderContainer = styled.div`
  margin: 0;
  border-radius: 0;
  padding: 1.5rem 2rem;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(231, 234, 237, 0.7);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  /* Mobile-friendly header */
  @media (max-width: 768px) {
    padding: 1rem;

    h2 {
      font-size: 1.25rem;
    }
  }
`;

export const MetadataRow = styled.div`
  display: flex;
  gap: 2rem;
  color: #6c757d;
  margin-top: 0.5rem;
  font-size: 0.9rem;

  span {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: color 0.2s ease;
    &:hover {
      color: ${OS_LEGAL_COLORS.primaryBlue};
    }

    svg {
      opacity: 0.7;
    }
  }

  /* Stack metadata on small screens */
  @media (max-width: 480px) {
    flex-wrap: wrap;
    gap: 0.75rem;

    span {
      font-size: 0.8rem;
    }
  }
`;

export const ContentArea = styled.div`
  display: flex;
  flex-direction: column;
  height: calc(100vh - 90px);
  background: white;
  position: relative;

  /* Stack layout on mobile */
  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

export const MainContentArea = styled.div`
  flex: 1;
  overflow-y: auto;
  position: relative;
`;

export const SummaryContent = styled.div`
  max-width: 800px;
  margin: 0 auto;
  padding: 1rem;
  transition: all 0.3s ease;

  &.dimmed {
    opacity: 0.4;
    transform: scale(0.98);
    filter: blur(1px);
  }
`;
