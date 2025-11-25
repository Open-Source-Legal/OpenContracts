import React from "react";
import { useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import styled from "styled-components";
import { ArrowLeft } from "lucide-react";
import { ThreadList } from "../threads/ThreadList";
import { ThreadDetail } from "../threads/ThreadDetail";
import { CreateThreadButton } from "../threads/CreateThreadButton";
import { selectedThreadId } from "../../graphql/cache";
import { clearThreadSelection } from "../../utils/navigationUtils";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
`;

const Header = styled.div`
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  background: #f8fafc;
`;

const Title = styled.h3`
  font-size: 1rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
`;

const BackButton = styled.button`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: white;
  color: #64748b;
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #f8fafc;
    border-color: #4a90e2;
    color: #0f172a;
  }
`;

const Content = styled.div`
  flex: 1;
  overflow-y: auto;
  min-height: 0; // Critical for flex child scrolling
`;

interface DocumentDiscussionsContentProps {
  documentId: string;
  corpusId?: string;
}

/**
 * DocumentDiscussionsContent - Sidebar content for document discussions
 *
 * This component bridges the sidebar UI with the thread system, handling:
 * - Thread list display (when no thread selected)
 * - Thread detail display (when thread selected via ?thread= param)
 * - Navigation between list and detail
 * - Back button to return to list
 *
 * @param documentId - ID of the document to display discussions for
 * @param corpusId - Optional corpus ID for context
 *
 * @example
 * <DocumentDiscussionsContent documentId="doc-123" corpusId="corpus-456" />
 *
 * Features:
 * - Query param based navigation (?thread=threadId)
 * - Auto-open sidebar when thread param detected (handled by parent)
 * - Compact layouts optimized for sidebar width
 */
export const DocumentDiscussionsContent: React.FC<
  DocumentDiscussionsContentProps
> = ({ documentId, corpusId }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const threadId = useReactiveVar(selectedThreadId);

  const handleThreadClick = (clickedThreadId: string) => {
    // Update URL query param
    const searchParams = new URLSearchParams(location.search);
    searchParams.set("thread", clickedThreadId);
    navigate({ search: searchParams.toString() }, { replace: true });
  };

  const handleBack = () => {
    // Clear thread selection, return to list
    clearThreadSelection(location, navigate);
  };

  return (
    <Container id="chat-container">
      <Header>
        {threadId ? (
          <BackButton onClick={handleBack} aria-label="Back to thread list">
            <ArrowLeft size={14} />
            Back to List
          </BackButton>
        ) : (
          <Title>Document Discussions</Title>
        )}

        {!threadId && corpusId && (
          <CreateThreadButton corpusId={corpusId} variant="secondary" />
        )}
      </Header>

      <Content>
        {threadId ? (
          <ThreadDetail
            conversationId={threadId}
            documentId={documentId}
            compact // Narrower layout for sidebar
          />
        ) : (
          <ThreadList
            documentId={documentId}
            onThreadClick={handleThreadClick}
            embedded // Compact cards for sidebar
          />
        )}
      </Content>
    </Container>
  );
};
