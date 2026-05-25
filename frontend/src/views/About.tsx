import React from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../assets/configurations/osLegalStyles";
import { PageContainer } from "../components/layout/PageLayout";
import { CiteMark } from "../components/brand/CiteMark";
import { useLandingContent } from "../config/landingContent";
import { renderInlineMarkup } from "../config/landingContent/renderInlineMarkup";

/**
 * /about — long-form positioning copy.
 *
 * Content is driven by the active landingContent variant
 * (`src/config/landingContent`). The default variant pitches *cite* as a
 * citation graph for document repositories in general (the world-facing
 * OSS framing). Deployments targeting end-users for a specific corpus
 * — e.g. `cite.opensource.legal` for the public record — override via
 * `REACT_APP_LANDING_VARIANT`.
 */

const Article = styled.article`
  max-width: 640px;
  margin: 0 auto;
  padding: 80px 24px 120px;

  @media (max-width: 768px) {
    padding: 48px 16px 80px;
  }
`;

const Eyebrow = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 36px;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 10px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const PageTitle = styled.h1`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 42px;
  line-height: 1.1;
  letter-spacing: -0.5px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 12px;

  @media (max-width: 768px) {
    font-size: 32px;
  }
`;

const Lede = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 17px;
  line-height: 1.7;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 56px;

  em {
    font-style: italic;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const Section = styled.section`
  margin-top: 56px;

  &:first-of-type {
    margin-top: 0;
  }
`;

const SectionTitle = styled.h2`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 23px;
  line-height: 1.25;
  letter-spacing: -0.25px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 20px;
`;

const Body = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 16px;
  line-height: 1.65;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 20px;

  em {
    font-style: italic;
  }

  a {
    color: ${OS_LEGAL_COLORS.accent};
    text-decoration: none;
    border-bottom: 1px solid ${OS_LEGAL_COLORS.accent};

    &:hover {
      color: ${OS_LEGAL_COLORS.accentHover};
    }
  }
`;

const FooterLinks = styled.div`
  margin-top: 80px;
  padding-top: 28px;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  flex-wrap: wrap;
  gap: 8px 0;
  align-items: center;

  a {
    color: ${OS_LEGAL_COLORS.accent};
    text-decoration: none;

    &:hover {
      color: ${OS_LEGAL_COLORS.accentHover};
    }
  }

  span[aria-hidden="true"] {
    margin: 0 10px;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

export const About: React.FC = () => {
  const { about } = useLandingContent();

  return (
    <PageContainer>
      <Article>
        <Eyebrow>
          <CiteMark size={14} ariaLabel="" />
          {about.eyebrow}
        </Eyebrow>
        <PageTitle>{about.title}</PageTitle>
        <Lede>{renderInlineMarkup(about.lede)}</Lede>

        {about.sections.map((section, sectionIndex) => (
          <Section key={`${sectionIndex}-${section.title}`}>
            <SectionTitle>{section.title}</SectionTitle>
            {section.paragraphs.map((paragraph, paraIndex) => (
              <Body key={`${sectionIndex}-${paraIndex}`}>
                {renderInlineMarkup(paragraph)}
              </Body>
            ))}
          </Section>
        ))}

        <FooterLinks>
          {about.footerLinks.map((link, index) => (
            <React.Fragment key={link.href}>
              {index > 0 && <span aria-hidden="true">·</span>}
              {link.internal ? (
                <Link to={link.href}>{link.label}</Link>
              ) : (
                <a
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${link.label} (opens in new window)`}
                >
                  {link.label}
                </a>
              )}
            </React.Fragment>
          ))}
        </FooterLinks>
      </Article>
    </PageContainer>
  );
};

export default About;
