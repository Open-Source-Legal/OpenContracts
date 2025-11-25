import React from "react";
import styled from "styled-components";
import { MessageSquare } from "lucide-react";
import { ThreadSearch } from "../components/search/ThreadSearch";
import { color } from "../theme/colors";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;

  @media (max-width: 1024px) {
    padding: 1.5rem;
  }

  @media (max-width: 768px) {
    padding: 1rem;
  }
`;

const Header = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 2px solid ${color.N4};

  @media (max-width: 768px) {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
  }
`;

const TitleSection = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
`;

const Title = styled.h1`
  font-size: 2rem;
  font-weight: 700;
  color: ${color.N10};
  margin: 0;
  letter-spacing: -0.025em;

  @media (max-width: 768px) {
    font-size: 1.5rem;
  }
`;

const Subtitle = styled.p`
  font-size: 1rem;
  color: ${color.N7};
  margin: 0;
  line-height: 1.5;

  @media (max-width: 768px) {
    font-size: 0.9375rem;
  }
`;

const SearchContainer = styled.div`
  flex: 1;
  overflow: auto;
`;

/**
 * ThreadSearchRoute - Standalone page for searching discussions
 *
 * This route provides a dedicated search page for finding discussion threads
 * across all corpuses and documents the user has access to.
 *
 * @example
 * <Route path="/threads" element={<ThreadSearchRoute />} />
 *
 * Features:
 * - Global search across all accessible discussions
 * - Advanced filtering by corpus and conversation type
 * - Paginated results
 * - Responsive design
 */
export function ThreadSearchRoute() {
  return (
    <Container>
      <Header>
        <TitleSection>
          <MessageSquare size={32} />
          <Title>Search Discussions</Title>
        </TitleSection>
        <Subtitle>
          Find discussion threads across all corpuses and documents you have
          access to
        </Subtitle>
      </Header>

      <SearchContainer>
        <ThreadSearch />
      </SearchContainer>
    </Container>
  );
}
