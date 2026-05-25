import React from "react";
import styled from "styled-components";
import { Link, useNavigate } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { useEnv } from "../hooks/UseEnv";
import { CiteMark } from "../brand/CiteMark";

interface CallToActionProps {
  isAuthenticated?: boolean;
}

/**
 * Landing-page tail — cite rebrand.
 *
 * Replaces the previous "Ready to dive in?" gradient/rocket block. Per
 * `01_brand/brand_system.md`: no marketing exclamations, no rocket-ship
 * verbs, no marketing gradients. Two restated paragraphs from
 * `02_copy/home_page.md` set the frame, followed by a quiet pair of
 * sign-in / browse actions that respects the editorial voice.
 */

const Section = styled.section`
  background: ${OS_LEGAL_COLORS.background};
  padding: 64px 0 16px;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  margin-top: 24px;

  @media (max-width: 768px) {
    padding: 48px 0 8px;
  }
`;

const Inner = styled.div`
  max-width: 640px;
  margin: 0 auto;
  padding: 0 4px;
`;

const Eyebrow = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 10px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const Headline = styled.p`
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
  font-size: 22px;
  font-weight: 400;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 20px;

  em {
    font-style: italic;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const Body = styled.p`
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
  font-size: 16px;
  line-height: 1.65;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 32px;

  em {
    font-style: italic;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
`;

const PrimaryButton = styled.button`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px;
  font-weight: 500;
  color: #fafaf7;
  background: #0f172a;
  border: none;
  border-radius: 6px;
  padding: 10px 18px;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: #1e293b;
  }
`;

const SecondaryLink = styled(Link)`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.accent};
  background: transparent;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  padding: 10px 18px;
  text-decoration: none;
  transition: border-color 0.15s ease, color 0.15s ease;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.accent};
    color: ${OS_LEGAL_COLORS.accentHover};
  }
`;

export const CallToAction: React.FC<CallToActionProps> = ({
  isAuthenticated,
}) => {
  const navigate = useNavigate();
  const { REACT_APP_USE_AUTH0 } = useEnv();
  const { loginWithRedirect } = useAuth0();

  const handleGetStarted = () => {
    if (REACT_APP_USE_AUTH0) {
      loginWithRedirect();
    } else {
      navigate("/login");
    }
  };

  // Anonymous visitors get the sign-in/browse pair. Authenticated users
  // already have the product surface; rendering the tail block for them
  // would be filler.
  if (isAuthenticated) {
    return null;
  }

  return (
    <Section>
      <Inner>
        <Eyebrow>
          <CiteMark size={14} ariaLabel="" />
          About cite
        </Eyebrow>
        <Headline>
          <em>cite</em> is built like infrastructure rather than a product.
        </Headline>
        <Body>
          The same way <em>OpenStreetMap</em> is the layer underneath every
          modern map, <em>cite</em> is the layer underneath every tool that has
          to read the public record — research tools, drafting tools, AI agents,
          civic technology, the next generation of legal practice. Use it
          directly through the search and the corpus browser. Build on top of it
          through the API. Contribute to it through annotation.
        </Body>
        <ButtonGroup>
          <PrimaryButton onClick={handleGetStarted}>
            Sign in to contribute
          </PrimaryButton>
          <SecondaryLink to="/about">Read the full story</SecondaryLink>
        </ButtonGroup>
      </Inner>
    </Section>
  );
};
