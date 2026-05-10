import React from "react";
import styled from "styled-components";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { mediaQuery } from "../corpuses/styles/corpusDesignTokens";

interface CardLayoutProps {
  children?: React.ReactChild | React.ReactChild[];
  Modals?: React.ReactChild | React.ReactChild[];
  BreadCrumbs?: React.ReactChild | null | undefined;
  SearchBar?: React.ReactChild;
  style?: React.CSSProperties;
}

const StyledSegment = styled.div`
  border: none;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  margin-bottom: 1rem;
  border-radius: 12px;
  background: #ffffff;
  padding: 1rem;
  transition: all 0.2s ease;

  &:hover {
    background: #ffffff;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.08);
  }

  /* Style for breadcrumb links */
  .breadcrumb {
    a {
      color: var(--text-primary, #1a2433);
      opacity: 0.85;
      transition: all 0.2s ease;

      &:hover {
        opacity: 1;
        transform: translateY(-1px);
      }
    }

    .active {
      color: var(--text-primary, #1a2433);
      font-weight: 500;
    }

    .divider {
      opacity: 0.5;
      margin: 0 0.5em;
    }
  }
`;

const SearchBarWrapper = styled.div`
  width: 100%;
  margin-bottom: 1rem;
`;

const ScrollableSegment = styled(StyledSegment)`
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  width: 100%;
  border-radius: 12px;
  background: #ffffff;
  margin: 0;
`;

export const CardLayout: React.FC<CardLayoutProps> = ({
  children,
  Modals,
  BreadCrumbs,
  SearchBar,
  style,
}) => {
  const { width } = useWindowDimensions();
  const use_mobile = width <= 600;

  return (
    <CardContainer
      width={width}
      className="CardLayoutContainer"
      style={{ ...style }}
    >
      {Modals}
      {SearchBar && <SearchBarWrapper>{SearchBar}</SearchBarWrapper>}
      {BreadCrumbs && (!use_mobile || width > 768) && (
        <StyledSegment
          style={{
            borderBottom: `1px solid ${OS_LEGAL_COLORS.border}`,
            background: "#f8f9fa",
          }}
        >
          {BreadCrumbs}
        </StyledSegment>
      )}
      <ScrollableSegment
        id="ScrollableSegment"
        style={{
          padding: 0,
          marginBottom: 0,
          boxShadow: "0 2px 8px rgba(0, 0, 0, 0.12)",
        }}
        className="CardHolder"
      >
        {children}
      </ScrollableSegment>
    </CardContainer>
  );
};

type CardContainerArgs = {
  width: number;
};

// Natural-flow container — let content stack and the document scroll naturally
// rather than forcing a viewport-stuck flex chain with internal scroll panels.
// The App shell already provides a sticky-footer outer (min-height: 100vh).
const CardContainer = styled.div<CardContainerArgs>(({ width }) => {
  const padding =
    width <= 600 ? "0.25rem" : width <= 1000 ? "0.5rem" : "0.75rem";

  return `
    display: flex;
    width: 100%;
    flex: 1;
    flex-direction: column;
    align-items: stretch;
    background-color: #f0f2f5;
    box-sizing: border-box;
    padding: ${padding};
  `;
});

export default CardLayout;
