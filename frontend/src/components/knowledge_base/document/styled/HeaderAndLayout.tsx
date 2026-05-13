import styled from "styled-components";
import { Z_INDEX } from "../../../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export const HeaderContainer = styled.div`
  margin: 0;
  border-radius: 0;
  padding: 1rem 1.25rem 0.875rem;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  position: relative;
  z-index: ${Z_INDEX.HEADER};
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.45rem;
  flex-shrink: 0;
  min-width: 0;

  @media (max-width: 768px) {
    padding: 0.875rem 1rem 0.75rem;
    gap: 0.4rem;
  }

  @media (max-width: 480px) {
    padding: 0.7rem 0.8rem 0.6rem;
  }
`;

export const HeaderPrimaryRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-width: 0;
`;

export const HeaderTitleBlock = styled.div`
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
`;

export const HeaderTitle = styled.h2`
  margin: 0;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 1.375rem;
  font-weight: 700;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  span {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  @media (max-width: 480px) {
    font-size: 1.2rem;
  }
`;

export const MetadataRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  column-gap: 1rem;
  row-gap: 0.35rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0;
  font-size: 0.82rem;
  line-height: 1.2;
  min-width: 0;

  > span {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    min-width: 0;
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: color 0.2s ease;

    &:hover {
      color: ${OS_LEGAL_COLORS.textTertiary};
    }

    svg {
      width: 14px;
      height: 14px;
      flex-shrink: 0;
      color: ${OS_LEGAL_COLORS.textMuted};
    }
  }

  @media (max-width: 768px) {
    column-gap: 0.875rem;
    row-gap: 0.3rem;
    font-size: 0.78rem;
  }

  @media (max-width: 480px) {
    column-gap: 0.75rem;

    .metadata-created-prefix {
      display: none;
    }
  }
`;

export const ContentArea = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: auto;
  background: white;
  position: relative;
  overflow: hidden;

  /* Stack layout on mobile */
  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

export const MainContentArea = styled.div`
  flex: 1;
  min-height: 0;
  overflow: hidden;
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
