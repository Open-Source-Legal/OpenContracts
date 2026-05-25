import styled from "styled-components";
import { Link } from "react-router-dom";

import useWindowDimensions from "../hooks/WindowDimensionHook";
import { OS_LEGAL_TYPOGRAPHY } from "../../assets/configurations/osLegalStyles";

// Stacked opensource.legal + [cite] lockup used in the footer. Matches the
// production SVG in /assets/brand/lockup.svg but inlined so it inherits the
// dark footer background color via CSS rather than the SVG's hard-coded fill.
const Lockup = styled.div<{ $small?: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: ${(props) => (props.$small ? "2px" : "6px")};
  margin: 0 auto 1.25em;
  padding: 0;
  color: rgba(255, 255, 255, 0.85);
`;

const LockupHandle = styled.span<{ $small?: boolean }>`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: ${(props) => (props.$small ? "10px" : "12px")};
  font-weight: 400;
  letter-spacing: 0.8px;
  color: rgba(255, 255, 255, 0.55);
`;

const LockupWordmark = styled.span<{ $small?: boolean }>`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: ${(props) => (props.$small ? "28px" : "36px")};
  font-weight: 400;
  letter-spacing: -0.5px;
  line-height: 1;
  color: rgba(255, 255, 255, 0.9);
`;

const FooterContainer = styled.footer<{ $compact?: boolean }>`
  width: 100%;
  padding: ${(props) => (props.$compact ? "1em" : "5em 0em")};
  background: #1b1c1d;
  color: rgba(255, 255, 255, 0.9);
`;

const FooterInner = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1em;
  text-align: center;
`;

const FooterGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 2em;
  text-align: left;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
    text-align: center;
  }
`;

const FooterHeading = styled.h4`
  color: rgba(255, 255, 255, 0.9);
  font-size: 1.1em;
  margin-bottom: 0.75em;
`;

const FooterLinkList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;

  li {
    margin-bottom: 0.5em;
  }

  a {
    color: rgba(255, 255, 255, 0.7);
    text-decoration: none;

    &:hover {
      color: rgba(255, 255, 255, 1);
    }
  }
`;

const FooterDivider = styled.hr`
  border: none;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  margin: 2em 0;
`;

const InlineLinks = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  justify-content: center;
  gap: 1em;
  flex-wrap: wrap;
  font-size: 0.9em;

  a {
    color: rgba(255, 255, 255, 0.7);
    text-decoration: none;

    &:hover {
      color: rgba(255, 255, 255, 1);
    }
  }
`;

export function Footer() {
  const { width } = useWindowDimensions();

  const isCompact = width <= 1000;
  const isSmall = width <= 400;

  const lockup = (
    <Lockup $small={isSmall} aria-label="opensource.legal [cite]">
      <LockupHandle $small={isSmall}>opensource.legal</LockupHandle>
      <LockupWordmark $small={isSmall}>[cite]</LockupWordmark>
    </Lockup>
  );

  const inlineLinks = (
    <InlineLinks>
      <li>
        <Link to="/about">About</Link>
      </li>
      <li>
        <Link to="/terms_of_service">Terms of Service</Link>
      </li>
      <li>
        <Link to="/privacy">Privacy Policy</Link>
      </li>
    </InlineLinks>
  );

  const orgBlock = (
    <>
      <div>
        <FooterHeading>opensource.legal</FooterHeading>
        <FooterLinkList>
          <li>
            <a
              href="https://github.com/Open-Source-Legal"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
          </li>
          <li>
            <Link to="/about">About cite</Link>
          </li>
        </FooterLinkList>
      </div>
      <div>
        <FooterHeading>opensource.legal &copy; 2021–2026</FooterHeading>
        <p>
          The citation layer underneath the public record. Originally shipped as
          Open Contracts; renamed to <em>cite</em> for v3. Built by{" "}
          <a href="https://github.com/JSv4">JSv4</a> and contributors. Use of
          this tool is governed by the terms of service.
        </p>
      </div>
    </>
  );

  if (isCompact) {
    return (
      <FooterContainer $compact>
        <FooterInner>
          {lockup}
          {inlineLinks}
          <FooterDivider />
          <FooterGrid>{orgBlock}</FooterGrid>
        </FooterInner>
      </FooterContainer>
    );
  }

  return (
    <FooterContainer>
      <FooterInner>
        <FooterGrid>{orgBlock}</FooterGrid>
        <FooterDivider />
        {lockup}
        {inlineLinks}
      </FooterInner>
    </FooterContainer>
  );
}
