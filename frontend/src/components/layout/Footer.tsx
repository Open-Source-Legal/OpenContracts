import styled from "styled-components";
import { Link } from "react-router-dom";

import logo from "../../assets/images/os_legal_128.png";
import useWindowDimensions from "../hooks/WindowDimensionHook";

const CenteredImage = styled.img<{ $small?: boolean }>`
  display: block;
  margin: 0 auto;
  max-width: 100%;
  height: auto;
  width: ${(props) => (props.$small ? "auto" : "150px")};
  ${(props) => props.$small && "height: 50px;"}
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

  if (width <= 1000) {
    return (
      <FooterContainer $compact>
        <FooterInner>
          <CenteredImage
            src={logo}
            alt="Open Contracts Logo"
            $small={width <= 400}
          />
          <InlineLinks>
            <li>
              <Link to="/">Site Map</Link>
            </li>
            <li>
              <Link to="/contact">Contact Us</Link>
            </li>
            <li>
              <Link to="/terms_of_service">Terms of Service</Link>
            </li>
            <li>
              <Link to="/privacy">Privacy Policy</Link>
            </li>
          </InlineLinks>
          <FooterDivider />
          <FooterGrid>
            <div>
              <FooterHeading>Open Source Legaltech</FooterHeading>
              <FooterLinkList>
                <li>
                  <a href="https://github.com/Open-Source-Legal">Github</a>
                </li>
              </FooterLinkList>
            </div>
            <div>
              <FooterHeading>OpenSource.Legal &copy;2021-2026</FooterHeading>
              <p>
                Open Contracts was developed by{" "}
                <a href="https://github.com/JSv4">JSv4</a>. Use of this tool is
                governed by the terms of service.
              </p>
            </div>
          </FooterGrid>
        </FooterInner>
      </FooterContainer>
    );
  } else {
    return (
      <FooterContainer>
        <FooterInner>
          <FooterGrid>
            <div>
              <FooterHeading>Open Source Legaltech</FooterHeading>
              <FooterLinkList>
                <li>
                  <a href="https://github.com/Open-Source-Legal">Github</a>
                </li>
              </FooterLinkList>
            </div>
            <div>
              <FooterHeading>OpenSource.Legal &copy;2021-2026</FooterHeading>
              <p>
                Open Contracts was developed by{" "}
                <a href="https://github.com/JSv4">JSv4</a>. Use of this tool is
                governed by the terms of service.
              </p>
            </div>
          </FooterGrid>
          <FooterDivider />
          <CenteredImage src={logo} alt="Open Contracts Logo" />
          <InlineLinks>
            <li>
              <Link to="/">Site Map</Link>
            </li>
            <li>
              <Link to="/contact">Contact Us</Link>
            </li>
            <li>
              <Link to="/terms_of_service">Terms of Service</Link>
            </li>
            <li>
              <Link to="/privacy">Privacy Policy</Link>
            </li>
          </InlineLinks>
        </FooterInner>
      </FooterContainer>
    );
  }
}
