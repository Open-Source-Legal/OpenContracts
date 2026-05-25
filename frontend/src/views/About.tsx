import React from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { PageContainer } from "../components/layout/PageLayout";
import { CiteMark } from "../components/brand/CiteMark";

/**
 * /about — the page linked from the footer and read by every contributor
 * before they decide whether to commit. Copy is the verbatim long-form
 * from `02_copy/about.md` in the cite rebrand handoff. Names incumbents
 * directly; treat this as the canonical reference for the project's
 * editorial voice.
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
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
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
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
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
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
  font-size: 23px;
  line-height: 1.25;
  letter-spacing: -0.25px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 20px;
`;

const Body = styled.p`
  font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
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

/**
 * Renders an inline `cite` reference. Italicized using Source Serif so it
 * reads as a publication name in body text, per the brand voice rules.
 */
const CiteName: React.FC = () => <em>cite</em>;

export const About: React.FC = () => {
  return (
    <PageContainer>
      <Article>
        <Eyebrow>
          <CiteMark size={14} ariaLabel="" />
          About
        </Eyebrow>
        <PageTitle>The citation graph belongs in the public domain.</PageTitle>
        <Lede>
          <CiteName /> is the open commons of the citation graph of the public
          record. This page is the long version — the one foundations and
          contributors read before they commit.
        </Lede>

        <Section>
          <SectionTitle>Why cite exists</SectionTitle>
          <Body>
            Every public document cites other public documents. Statutes cite
            the acts that authorized them. Court opinions cite the precedents
            that bound them. Contracts cite the statutes that govern them.
            Research papers cite the work that made them possible. Patents cite
            the prior art they extend. Technical standards cite the RFCs they
            build on. Government budgets cite the acts that authorize their line
            items. The web of citation is, quite literally, how public knowledge
            accumulates.
          </Body>
        </Section>

        <Section>
          <SectionTitle>Why it&rsquo;s broken</SectionTitle>
          <Body>
            That web has been fragmented across closed databases for fifty
            years. <em>Westlaw</em> and <em>Lexis</em> own the legal slice
            between them. <em>JSTOR</em> and the academic publishers own the
            scholarly slice. <em>USPTO</em> holds the patent record itself, but
            the relationship data — what cites what — sits behind commercial
            vendors. Each of these companies charges professionals to access a
            graph that, by every reasonable measure, belongs in the public
            domain.
          </Body>
          <Body>
            <em>Wheaton v. Peters</em> (1834) established that judicial opinions
            are uncopyrightable. Statutes have never been copyrightable.
            Government records have never been copyrightable. The proprietary
            citators have built lucrative businesses on the position that their{" "}
            <em>compilation</em> of the relationships between those public
            documents is theirs. That position has been challenged repeatedly —
            most recently by <em>Public.Resource.Org</em> and the{" "}
            <em>Free Law Project</em> — and it&rsquo;s slowly losing.
          </Body>
        </Section>

        <Section>
          <SectionTitle>What cite is</SectionTitle>
          <Body>
            <CiteName /> is the open commons of the citation graph. Every
            public-domain document that cites another, surfaced as one open
            network. Documents are nodes. Citations are edges. Built like{" "}
            <em>OpenStreetMap</em> — open license, contributor-owned,
            infrastructure-grade — for the public record. Where the proprietary
            citators charge by the lookup, <CiteName /> is the layer underneath.
            Where the proprietary citators close off the graph, <CiteName />{" "}
            publishes it.
          </Body>
        </Section>

        <Section>
          <SectionTitle>Why we think we can do this</SectionTitle>
          <Body>
            The citation graph of the public record is mostly assembly work. The
            underlying documents are already public. The relationships between
            them have been observed by every professional who has ever read one
            — every brief filed, every paper cited, every contract executed has
            someone tracing edges by hand. Aggregating that work, normalizing
            it, and publishing it is a project of scope rather than novelty. The
            community has been waiting for the tool. <em>opensource.legal</em>{" "}
            is the project that builds it.
          </Body>
        </Section>

        <FooterLinks>
          <span>
            Browse the{" "}
            <a
              href="https://open-source-legal.github.io/OpenContracts/"
              target="_blank"
              rel="noopener noreferrer"
            >
              docs
            </a>
          </span>
          <span aria-hidden="true">·</span>
          <span>
            <Link to="/corpuses">Open a corpus</Link>
          </span>
          <span aria-hidden="true">·</span>
          <span>
            <a
              href="https://github.com/Open-Source-Legal/OpenContracts"
              target="_blank"
              rel="noopener noreferrer"
            >
              Contribute on GitHub
            </a>
          </span>
        </FooterLinks>
      </Article>
    </PageContainer>
  );
};

export default About;
