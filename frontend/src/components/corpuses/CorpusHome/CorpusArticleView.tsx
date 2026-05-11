/**
 * CorpusArticleView — Renders a CAML article stored as Readme.CAML
 * in the corpus documents.
 *
 * Fetches the Readme.CAML document, parses its content, and renders
 * the full scrollytelling article experience.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@apollo/client";
import { ArrowLeft, FileText, Edit } from "lucide-react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

import {
  GET_CORPUS_ARTICLE,
  GetCorpusArticleInput,
  GetCorpusArticleOutput,
} from "../../../graphql/queries";
import { CorpusType } from "../../../types/graphql-api";
import { parseCaml } from "@os-legal/caml";
import type { CamlDocument } from "@os-legal/caml";
import { CAML_ARTICLE_FILENAME } from "../../../assets/configurations/constants";
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
`;

const ToolbarNav = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: auto;
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
      return parseCaml(camlContent);
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
        </ToolbarNav>
      </ArticleToolbar>
      {showDocumentsButton && (
        <ArticleDocumentsDrawer
          corpusId={corpus.id}
          open={docsDrawerOpen}
          onClose={() => setDocsDrawerOpen(false)}
        />
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
