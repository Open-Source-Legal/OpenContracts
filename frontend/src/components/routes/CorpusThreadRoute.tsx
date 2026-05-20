import React from "react";
import { useNavigate, Link } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { mediaQuery } from "../corpuses/styles/corpusDesignTokens";
import { ArrowLeft, Folder, ChevronRight } from "lucide-react";
import {
  openedCorpus,
  openedThread,
  routeLoading,
  routeError,
} from "../../graphql/cache";
import { ThreadDetail } from "../threads/ThreadDetail";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { getCorpusUrl } from "../../utils/navigationUtils";

const Container = styled.div`
  margin: 0 auto;
  padding: 0;
  height: 100%;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
`;

const NavBar = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.5rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};

  ${mediaQuery.tablet} {
    padding: 0.5rem 1rem;
    flex-wrap: wrap;
  }
`;

const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.625rem;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: white;
  color: #374151;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

  &:hover {
    background: ${OS_LEGAL_COLORS.gray50};
    border-color: ${OS_LEGAL_COLORS.green};
    color: ${OS_LEGAL_COLORS.successText};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const NavSeparator = styled.span`
  color: #9ca3af;
  display: flex;
  align-items: center;

  svg {
    width: 14px;
    height: 14px;
  }
`;

const CorpusLink = styled(Link)`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.375rem 0.625rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textTertiary};
  text-decoration: none;
  transition: all 0.15s;
  min-width: 0;
  max-width: 100%;

  &:hover {
    background: ${OS_LEGAL_COLORS.border};
    border-color: ${OS_LEGAL_COLORS.borderHover};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 12px;
    height: 12px;
    flex-shrink: 0;
  }

  ${mediaQuery.tablet} {
    flex: 1 1 auto;
    min-width: 0;
  }
`;

const CorpusLinkLabel = styled.span`
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  max-width: 100%;
`;

const ThreadLabel = styled.span`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-weight: 500;
`;

/**
 * CorpusThreadRoute - DUMB CONSUMER route for viewing corpus discussion threads
 *
 * URL Pattern: /c/:userIdent/:corpusIdent/discussions/:threadId
 *
 * This component is a DUMB CONSUMER following the One True Routing Mantra:
 * - NEVER uses useParams() to parse URLs (CentralRouteManager does this)
 * - NEVER fetches entities (CentralRouteManager Phase 1 handles this)
 * - ONLY READS reactive vars set by CentralRouteManager
 * - Renders loading/error states and delegates to ThreadDetail
 *
 * CentralRouteManager Phase 1 handles:
 * - Parsing /c/:userIdent/:corpusIdent/discussions/:threadId
 * - Fetching thread entity via GET_THREAD_DETAIL
 * - Fetching corpus entity for context
 * - Setting openedThread() and openedCorpus()
 *
 * @example
 * URL: /c/john/legal-contracts/discussions/thread-123
 * CentralRouteManager sets: openedThread(thread), openedCorpus(corpus)
 * This component: Reads reactive vars, renders UI
 */
export const CorpusThreadRoute: React.FC = () => {
  const navigate = useNavigate();

  // ONLY READ reactive vars (set by CentralRouteManager Phase 1)
  const thread = useReactiveVar(openedThread);
  const corpus = useReactiveVar(openedCorpus);
  const loading = useReactiveVar(routeLoading);
  const error = useReactiveVar(routeError);

  const handleBack = () => {
    if (corpus) {
      // Navigate back to corpus discussions tab using utility
      const url = getCorpusUrl(corpus, { tab: "discussions" });
      if (url !== "#") {
        navigate(url);
        return;
      }
    }
    // Fallback to browser history
    navigate(-1);
  };

  // Loading state
  if (loading) {
    return (
      <Container>
        <ModernLoadingDisplay type="default" message="Loading discussion..." />
      </Container>
    );
  }

  // Error state
  if (error || !thread) {
    return (
      <Container>
        <ModernErrorDisplay
          type="generic"
          error={error?.message || "Thread not found"}
          onRetry={() => window.location.reload()}
        />
      </Container>
    );
  }

  // Success state - render thread detail
  return (
    <Container>
      <NavBar>
        <BackButton onClick={handleBack} aria-label="Back to Discussions">
          <ArrowLeft />
          Back
        </BackButton>
        {corpus && (
          <>
            <NavSeparator>
              <ChevronRight />
            </NavSeparator>
            <CorpusLink
              to={`/c/${corpus.creator?.slug}/${corpus.slug}`}
              title={corpus.title}
            >
              <Folder />
              <CorpusLinkLabel>{corpus.title}</CorpusLinkLabel>
            </CorpusLink>
            <NavSeparator>
              <ChevronRight />
            </NavSeparator>
            <ThreadLabel>Discussion</ThreadLabel>
          </>
        )}
      </NavBar>

      <ThreadDetail conversationId={thread.id} corpusId={corpus?.id} />
    </Container>
  );
};
