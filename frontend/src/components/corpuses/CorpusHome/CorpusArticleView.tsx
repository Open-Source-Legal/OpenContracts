/**
 * CorpusArticleView — Renders a CAML article stored as Readme.CAML
 * in the corpus documents.
 *
 * Fetches the Readme.CAML document, parses its content, and renders
 * the full scrollytelling article experience.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@apollo/client";
import {
  ArrowLeft,
  FileText,
  Edit,
  Compass,
  LayoutDashboard,
  Menu,
} from "lucide-react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { HeroImageBand, PillToggle, PillToggleLabel } from "./styles";

import {
  GET_CORPUS_ARTICLE,
  GetCorpusArticleInput,
  GetCorpusArticleOutput,
} from "../../../graphql/queries";
import { CorpusType } from "../../../types/graphql-api";
import type { CamlDocument } from "@os-legal/caml";
import { parseCamlArticle } from "../caml/normalizeCamlSource";
import {
  CAML_ARTICLE_FILENAME,
  TABLET_BREAKPOINT,
} from "../../../assets/configurations/constants";
import { CamlDirectiveRenderer } from "../caml/CamlDirectiveRenderer";
import {
  registerDirectiveHandler,
  unregisterDirectiveHandler,
} from "../caml/directiveRegistry";
import { useCiteHandler } from "../caml/useCiteHandler";
import { ArticleDocumentsDrawer } from "./ArticleDocumentsDrawer";
import { CAML_COMPONENTS } from "../../../utils/camlComponentRegistry";

// ---------------------------------------------------------------------------
// Styled components
// ---------------------------------------------------------------------------

const ArticleViewContainer = styled.div`
  width: 100%;
  min-height: 100%;
  background: ${OS_LEGAL_COLORS.surface};
  overflow-x: hidden;
  box-sizing: border-box;
`;

const ArticleToolbar = styled.div`
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
`;

const ToolbarButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.875rem;
  border: none;
  border-radius: 9999px;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    transition: transform 0.2s ease;
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  &:active {
    transform: scale(0.97);
  }
`;

const BackButtonStyled = styled(ToolbarButton)`
  &:hover svg {
    transform: translateX(-2px);
  }
`;

const EditButtonStyled = styled(ToolbarButton)`
  color: ${OS_LEGAL_COLORS.accent};

  &:hover {
    background: ${OS_LEGAL_COLORS.accentSurface};
    color: ${OS_LEGAL_COLORS.accentHover};
  }
`;

const ToolbarTitle = styled.span`
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-weight: 400;
  letter-spacing: 0.01em;
  /* Shrink so the nav controls never get pushed off-screen on narrow viewports. */
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  /* Redundant with the article hero on mobile — hide to make room for nav controls. */
  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: none;
  }
`;

const ToolbarNav = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
  flex-shrink: 0;
`;

/** Mobile-only control opening the corpus tab menu; the sidebar is always
 *  present on desktop. This is deliberately NOT the shared `MobileMenuButton`
 *  from `styles.ts`: that button belongs to the legacy `CORPUS_COLORS` design
 *  language (a bare, background-less slate icon) used by `CorpusLandingView` /
 *  `CorpusDetailsView`. `CorpusArticleView` is rendered in the newer os-legal
 *  design system (`OS_LEGAL_COLORS`) and its toolbar sits beside os-legal
 *  `PillToggle` controls, so it uses a matching circular, filled button. Reusing
 *  `MobileMenuButton` here would visually clash with the article toolbar. */
const ToolbarMenuButton = styled.button`
  display: none;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 9999px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;

  &:hover {
    background: ${OS_LEGAL_COLORS.accentSurface};
    color: ${OS_LEGAL_COLORS.accent};
  }

  &:active {
    transform: scale(0.97);
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.accent};
    outline-offset: 2px;
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: inline-flex;
  }
`;

/** Centered corpus avatar shown above the article body when the CAML does not
 *  already reference the corpus icon. Restores the hero image that the corpus
 *  landing view shows automatically, so a Readme.CAML article doesn't silently
 *  drop the corpus's cover image. */
const HeroAvatarRow = styled.div`
  display: flex;
  justify-content: center;
  padding: 1.5rem 1rem 0;
`;

const LoadingContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 1rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 1rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
  padding: 2rem;
`;

const EmptyIcon = styled.div`
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface CorpusArticleViewProps {
  corpus: CorpusType;
  onBack: () => void;
  onEditArticle?: () => void;
  showDocumentsButton?: boolean;
  /**
   * Toggles power-user ("Manage") mode. When provided, an Explore/Manage pill
   * is rendered in the sticky toolbar. This lives in the toolbar (not as a
   * bottom-floating control) so it stays reachable on mobile, where a
   * position:fixed element inside the article's scroll container is unreliable.
   */
  onModeToggle?: () => void;
  /** Whether power-user ("Manage") mode is currently active. */
  isPowerUserMode?: boolean;
  /**
   * Opens the corpus tab menu (mobile navigation sidebar). When provided, a
   * mobile-only menu button is rendered in the sticky toolbar so the corpus
   * tabs stay reachable while the Readme.CAML article is the corpus home. The
   * sidebar only exists in power-user mode, so the button is gated on
   * isPowerUserMode to match CorpusLandingView / CorpusDetailsView.
   */
  onOpenMobileMenu?: () => void;
  stats?: {
    annotations?: number;
    documents?: number;
    contributors?: number;
    threads?: number;
  };
  testId?: string;
}

export const CorpusArticleView: React.FC<CorpusArticleViewProps> = ({
  corpus,
  onBack,
  onEditArticle,
  showDocumentsButton,
  onModeToggle,
  isPowerUserMode = false,
  onOpenMobileMenu,
  stats,
  testId = "corpus-article",
}) => {
  const [docsDrawerOpen, setDocsDrawerOpen] = useState(false);
  const [camlContent, setCamlContent] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Register the @cite directive handler for this component's lifecycle.
  // Registered in useEffect (not at module level) so it can be gated by
  // feature flags and properly cleaned up to avoid registry collisions in tests.
  useEffect(() => {
    registerDirectiveHandler("cite", useCiteHandler);
    return () => unregisterDirectiveHandler("cite");
  }, []);

  // Memoize handler context to prevent CamlDirectiveRenderer from
  // recreating renderMarkdown on every parent render.
  const handlerContext = useMemo(() => ({ corpusId: corpus.id }), [corpus.id]);

  // Query for Readme.CAML document in this corpus
  const queryVars = useMemo<GetCorpusArticleInput>(
    () => ({
      corpusId: corpus.id,
      title: CAML_ARTICLE_FILENAME,
    }),
    [corpus.id]
  );

  const { data, loading } = useQuery<
    GetCorpusArticleOutput,
    GetCorpusArticleInput
  >(GET_CORPUS_ARTICLE, {
    variables: queryVars,
  });

  const articleDoc = data?.documents?.edges?.[0]?.node;

  // Fetch the CAML content from the txtExtractFile URL
  useEffect(() => {
    if (!articleDoc?.txtExtractFile) {
      setCamlContent(null);
      return;
    }

    fetch(articleDoc.txtExtractFile)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => {
        setCamlContent(text);
        setFetchError(null);
      })
      .catch((err) => {
        console.error("Failed to fetch CAML content:", err);
        setFetchError(err.message);
        setCamlContent(null);
      });
  }, [articleDoc?.txtExtractFile]);

  // Parse CAML content
  const parsedDocument: CamlDocument | null = useMemo(() => {
    if (!camlContent) return null;
    try {
      return parseCamlArticle(camlContent);
    } catch (err) {
      console.error("Failed to parse CAML:", err);
      return null;
    }
  }, [camlContent]);

  // Resolve CAML image protocol URIs to actual URLs.
  // "corpus://icon" resolves to the corpus's icon URL.
  // "corpus://current" is an alias for "corpus://icon" — both resolve to the
  // active corpus's icon. The alias exists for semantic clarity in CAML content
  // where "current" refers to the corpus being viewed.
  const resolveImageSrc = useCallback(
    (src: string): string | undefined => {
      if (src === "corpus://icon" || src === "corpus://current") {
        return corpus.icon || undefined;
      }
      return undefined;
    },
    [corpus.icon]
  );

  // Whether the article body already surfaces the corpus icon (via a hero or
  // inline `corpus://icon` / `corpus://current` reference). When it does NOT,
  // we render the icon ourselves above the article so the corpus cover image
  // isn't lost just because the CAML author didn't embed it explicitly —
  // matching the auto-hero behavior of CorpusLandingView.
  const camlReferencesCorpusIcon = useMemo(
    () =>
      !!camlContent &&
      (camlContent.includes("corpus://icon") ||
        camlContent.includes("corpus://current")),
    [camlContent]
  );

  const showCorpusImage = Boolean(corpus.icon) && !camlReferencesCorpusIcon;

  if (loading) {
    return (
      <ArticleViewContainer data-testid={testId}>
        <ArticleToolbar>
          <BackButtonStyled onClick={onBack}>
            <ArrowLeft size={14} />
            Back
          </BackButtonStyled>
        </ArticleToolbar>
        <LoadingContainer>
          <p>Loading article...</p>
        </LoadingContainer>
      </ArticleViewContainer>
    );
  }

  if (!articleDoc || fetchError) {
    return (
      <ArticleViewContainer data-testid={testId}>
        <ArticleToolbar>
          <BackButtonStyled onClick={onBack}>
            <ArrowLeft size={14} />
            Back
          </BackButtonStyled>
        </ArticleToolbar>
        <EmptyState>
          <EmptyIcon>
            <FileText size={28} />
          </EmptyIcon>
          <p>No article found for this corpus.</p>
          <p
            style={{ fontSize: "0.8125rem", color: OS_LEGAL_COLORS.textMuted }}
          >
            Upload a <code>Readme.CAML</code> document to create one.
          </p>
        </EmptyState>
      </ArticleViewContainer>
    );
  }

  if (!parsedDocument) {
    return (
      <ArticleViewContainer data-testid={testId}>
        <ArticleToolbar>
          <BackButtonStyled onClick={onBack}>
            <ArrowLeft size={14} />
            Back
          </BackButtonStyled>
        </ArticleToolbar>
        <LoadingContainer>
          <p>Parsing article...</p>
        </LoadingContainer>
      </ArticleViewContainer>
    );
  }

  return (
    <ArticleViewContainer data-testid={testId}>
      <ArticleToolbar>
        <BackButtonStyled onClick={onBack}>
          <ArrowLeft size={14} />
          Back
        </BackButtonStyled>
        <ToolbarTitle>{corpus.title}</ToolbarTitle>
        <ToolbarNav>
          {showDocumentsButton && (
            <ToolbarButton onClick={() => setDocsDrawerOpen(true)}>
              <FileText size={14} />
              Documents
            </ToolbarButton>
          )}
          {onEditArticle && (
            <EditButtonStyled onClick={onEditArticle}>
              <Edit size={14} />
              Edit
            </EditButtonStyled>
          )}
          {/* Explore/Manage toggle — surfaces the corpus sidebar tabs. Lives in
              the sticky toolbar so it stays reachable on mobile (a bottom
              position:fixed control inside the scroll container is not). */}
          {onModeToggle && (
            <PillToggle
              onClick={onModeToggle}
              title={
                isPowerUserMode
                  ? "Switch to explore view"
                  : "Switch to corpus management view"
              }
              data-testid={`${testId}-mode-toggle`}
            >
              <PillToggleLabel $active={!isPowerUserMode}>
                <Compass size={12} />
                Explore
              </PillToggleLabel>
              <PillToggleLabel $active={isPowerUserMode}>
                <LayoutDashboard size={12} />
                Manage
              </PillToggleLabel>
            </PillToggle>
          )}
          {/* Mobile entry point to the nav sidebar — not present on desktop. */}
          {onOpenMobileMenu && isPowerUserMode && (
            <ToolbarMenuButton
              onClick={onOpenMobileMenu}
              aria-label="Open navigation menu"
              data-testid={`${testId}-mobile-menu`}
            >
              <Menu size={16} />
            </ToolbarMenuButton>
          )}
        </ToolbarNav>
      </ArticleToolbar>
      {showDocumentsButton && (
        <ArticleDocumentsDrawer
          corpusId={corpus.id}
          open={docsDrawerOpen}
          onClose={() => setDocsDrawerOpen(false)}
        />
      )}

      {showCorpusImage && corpus.icon && (
        <HeroAvatarRow data-testid={`${testId}-hero-image`}>
          <HeroImageBand>
            <img
              src={corpus.icon}
              alt={`${corpus.title || "Corpus"} cover image`}
              loading="lazy"
            />
          </HeroImageBand>
        </HeroAvatarRow>
      )}

      <CamlDirectiveRenderer
        document={parsedDocument}
        handlerContext={handlerContext}
        stats={stats}
        resolveImageSrc={resolveImageSrc}
        componentRegistry={CAML_COMPONENTS}
        bottomInset="var(--oc-article-bottom-clearance, 0px)"
      />
    </ArticleViewContainer>
  );
};
