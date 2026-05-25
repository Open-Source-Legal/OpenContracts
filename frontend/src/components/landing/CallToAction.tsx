import React from "react";
import styled from "styled-components";
import { Link, useNavigate } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import { useEnv } from "../hooks/UseEnv";
import { CiteMark } from "../brand/CiteMark";
import { useLandingContent } from "../../config/landingContent";
import { renderInlineMarkup } from "../../config/landingContent/renderInlineMarkup";

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
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
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
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
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
  color: ${OS_LEGAL_COLORS.warmPaper};
  background: ${OS_LEGAL_COLORS.ink};
  border: none;
  border-radius: 6px;
  padding: 10px 18px;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.inkHover};
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
  const { callToAction } = useLandingContent();

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
          {callToAction.eyebrow}
        </Eyebrow>
        <Headline>{renderInlineMarkup(callToAction.headline)}</Headline>
        <Body>{renderInlineMarkup(callToAction.body)}</Body>
        <ButtonGroup>
          <PrimaryButton onClick={handleGetStarted}>
            {callToAction.primaryLabel}
          </PrimaryButton>
          <SecondaryLink to={callToAction.secondaryPath}>
            {callToAction.secondaryLabel}
          </SecondaryLink>
        </ButtonGroup>
      </Inner>
    </Section>
  );
};
