import { Link } from "react-router-dom";
import styled from "styled-components";
import { Z_INDEX } from "../../../../assets/configurations/constants";
import { SHADOW } from "../../../../assets/configurations/designTokens";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../../assets/configurations/osLegalStyles";

export const HeaderContainer = styled.div`
  margin: 0;
  border-radius: 0;
  padding: 1rem 1.25rem 0.9rem;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(12px);
  /* Depth over borders: soft downward shadow instead of a hairline. */
  border-bottom: none;
  box-shadow: ${SHADOW.header};
  position: relative;
  z-index: ${Z_INDEX.HEADER};
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.55rem;
  flex-shrink: 0;
  min-width: 0;

  @media (max-width: 768px) {
    padding: 0.875rem 1rem 0.8rem;
    gap: 0.5rem;
  }

  @media (max-width: 480px) {
    padding: 0.75rem 0.85rem 0.7rem;
  }
`;

/**
 * Brand row pinned to the very top of the document header.
 *
 * The DocumentKnowledgeBase opens as a full-screen modal that sits above — and
 * therefore hides — the global NavMenu where the cite / opensource.legal
 * branding normally lives. We re-surface that branding here so the product
 * identity stays visible while a document is open.
 */
export const HeaderBrandRow = styled.div`
  display: flex;
  align-items: center;
  min-width: 0;
`;

export const BrandLink = styled(Link)`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  /* Pull the mark flush with the container's left padding so it optically
     aligns with the title row below it. */
  margin-left: -0.3rem;
  padding: 0.15rem 0.35rem;
  border-radius: 8px;
  text-decoration: none;
  color: ${OS_LEGAL_COLORS.textSecondary};
  transition: color 0.18s ease, background 0.18s ease;

  &:hover {
    color: ${OS_LEGAL_COLORS.textPrimary};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  svg {
    flex-shrink: 0;
  }
`;

export const BrandDomain = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 0.95rem;
  font-weight: 500;
  letter-spacing: -0.01em;
  white-space: nowrap;

  @media (max-width: 480px) {
    font-size: 0.85rem;
  }
`;

export const BrandAccent = styled.span`
  color: ${OS_LEGAL_COLORS.accent};
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
  font-size: 1.35rem;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.012em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  span {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  @media (max-width: 768px) {
    font-size: 1.25rem;
  }

  @media (max-width: 480px) {
    font-size: 1.15rem;
  }
`;

/**
 * Metadata row: soft-tinted chips (depth over borders) for filetype, creator
 * and created-date. The version selector is dropped in alongside them.
 */
export const MetadataRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 0.4rem;
  row-gap: 0.4rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.05rem;
  font-size: 0.78rem;
  line-height: 1.2;
  min-width: 0;

  > span {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    min-width: 0;
    max-width: 100%;
    padding: 0.22rem 0.55rem;
    border-radius: 999px;
    background: ${OS_LEGAL_COLORS.surfaceHover};
    box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.05);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;

    &:hover {
      background: ${OS_LEGAL_COLORS.surfaceLight};
      color: ${OS_LEGAL_COLORS.textTertiary};
      box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.08);
    }

    svg {
      width: 13px;
      height: 13px;
      flex-shrink: 0;
      color: ${OS_LEGAL_COLORS.accent};
    }
  }

  @media (max-width: 768px) {
    column-gap: 0.35rem;
    row-gap: 0.35rem;
    font-size: 0.74rem;
  }

  @media (max-width: 480px) {
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
