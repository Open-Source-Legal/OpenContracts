import React from "react";
import { useNavigate } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { ArrowLeft } from "lucide-react";
import {
  openedCorpus,
  openedThread,
  routeLoading,
  routeError,
} from "../../graphql/cache";
import { ThreadDetail } from "../threads/ThreadDetail";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";

const Container = styled.div`
  margin: 0 auto;
  padding: 0;
  height: 100%;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
`;

const BackButtonWrapper = styled.div`
  max-width: 100%;
  margin: 0 auto;
  padding: 1.5rem 10% 0;

  @media (max-width: 1600px) {
    padding: 1.5rem 5% 0;
  }

  @media (max-width: 1024px) {
    padding: 1rem 3% 0;
  }

  @media (max-width: 768px) {
    padding: 1rem 2% 0;
  }

  @media (max-width: 480px) {
    padding: 0.75rem 1% 0;
  }
`;

const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: white;
  color: #64748b;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #f8fafc;
    border-color: #4a90e2;
    color: #0f172a;
  }
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
    if (corpus?.creator?.slug && corpus?.slug) {
      // Navigate back to corpus discussions tab
      navigate(`/c/${corpus.creator.slug}/${corpus.slug}?tab=discussions`);
    } else {
      // Fallback to browser history
      navigate(-1);
    }
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
      <BackButtonWrapper>
        <BackButton onClick={handleBack} aria-label="Back to Discussions">
          <ArrowLeft size={16} />
          Back to Discussions
        </BackButton>
      </BackButtonWrapper>

      <ThreadDetail conversationId={thread.id} corpusId={corpus?.id} />
    </Container>
  );
};
