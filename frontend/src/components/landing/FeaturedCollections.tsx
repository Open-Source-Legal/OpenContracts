import React from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { getCorpusUrl } from "../../utils/navigationUtils";
import { CollectionCard, CollectionList } from "@os-legal/ui";
import type { CollectionType } from "@os-legal/ui";
import { GetTrendingCorpusesOutput } from "../../graphql/landing-queries";
import { color } from "../../theme/colors";

interface FeaturedCollectionsProps {
  corpuses: GetTrendingCorpusesOutput["corpuses"]["edges"] | null;
  loading?: boolean;
  selectedCategory?: string | null;
}

const Container = styled.div`
  width: 100%;
`;

const EmptyStateContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
  background: ${color.N2};
  border-radius: 16px;
  border: 2px dashed ${color.N4};
`;

const EmptyStateTitle = styled.h3`
  font-size: 1.25rem;
  font-weight: 600;
  color: ${color.N10};
  margin: 0 0 0.5rem 0;
`;

const EmptyStateDescription = styled.p`
  font-size: 1rem;
  color: ${color.N7};
  margin: 0;
`;

// Skeleton for loading state
const SkeletonCard = styled.div`
  background: white;
  border-radius: 12px;
  border: 1px solid ${color.N3};
  padding: 1.5rem;
  display: flex;
  gap: 1rem;
`;

const SkeletonIcon = styled.div`
  width: 48px;
  height: 48px;
  background: linear-gradient(
    90deg,
    ${color.N3} 25%,
    ${color.N4} 50%,
    ${color.N3} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 8px;

  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }
`;

const SkeletonContent = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const SkeletonLine = styled.div<{ $width?: string; $height?: string }>`
  width: ${(props) => props.$width || "100%"};
  height: ${(props) => props.$height || "16px"};
  background: linear-gradient(
    90deg,
    ${color.N3} 25%,
    ${color.N4} 50%,
    ${color.N3} 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
`;

// Map category name to CollectionType
function mapCategoryToType(categoryName?: string): CollectionType {
  if (!categoryName) return "default";

  const lowerName = categoryName.toLowerCase();
  if (lowerName.includes("legislation")) return "legislation";
  if (lowerName.includes("contract")) return "contracts";
  if (lowerName.includes("case") || lowerName.includes("law"))
    return "case-law";
  if (lowerName.includes("knowledge")) return "knowledge";

  return "default";
}

export const FeaturedCollections: React.FC<FeaturedCollectionsProps> = ({
  corpuses,
  loading,
  selectedCategory,
}) => {
  const navigate = useNavigate();

  // Filter by category if selected
  const filteredCorpuses = React.useMemo(() => {
    if (!corpuses) return [];
    if (!selectedCategory || selectedCategory === "all") return corpuses;

    return corpuses.filter(({ node }) =>
      node.categories?.some((cat) => cat.id === selectedCategory)
    );
  }, [corpuses, selectedCategory]);

  const handleCorpusClick = (
    corpus: GetTrendingCorpusesOutput["corpuses"]["edges"][0]["node"]
  ) => {
    const url = getCorpusUrl(corpus);
    if (url !== "#") {
      navigate(url);
    }
  };

  if (loading) {
    return (
      <Container>
        <CollectionList gap="md">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <SkeletonCard key={i}>
              <SkeletonIcon />
              <SkeletonContent>
                <SkeletonLine $width="60%" $height="20px" />
                <SkeletonLine $width="40%" $height="14px" />
                <SkeletonLine $width="100%" $height="14px" />
              </SkeletonContent>
            </SkeletonCard>
          ))}
        </CollectionList>
      </Container>
    );
  }

  if (filteredCorpuses.length === 0) {
    return (
      <Container>
        <EmptyStateContainer>
          <EmptyStateTitle>
            {selectedCategory
              ? "No collections in this category"
              : "No collections yet"}
          </EmptyStateTitle>
          <EmptyStateDescription>
            {selectedCategory
              ? "Try selecting a different category to see more collections."
              : "Be the first to create a document collection!"}
          </EmptyStateDescription>
        </EmptyStateContainer>
      </Container>
    );
  }

  return (
    <Container>
      <CollectionList gap="md">
        {filteredCorpuses.map(({ node: corpus }) => {
          // Get first category for badge and type
          const firstCategory = corpus.categories?.[0];
          const collectionType = mapCategoryToType(firstCategory?.name);

          // Build stats array
          const stats: string[] = [];
          if (corpus.documentCount) {
            stats.push(
              `${corpus.documentCount} doc${
                corpus.documentCount !== 1 ? "s" : ""
              }`
            );
          }
          if (corpus.annotationCount) {
            stats.push(
              `${corpus.annotationCount} annotation${
                corpus.annotationCount !== 1 ? "s" : ""
              }`
            );
          }
          if (corpus.engagementMetrics?.uniqueContributors) {
            stats.push(
              `${corpus.engagementMetrics.uniqueContributors} contributor${
                corpus.engagementMetrics.uniqueContributors !== 1 ? "s" : ""
              }`
            );
          }

          // Determine status
          const status =
            corpus.engagementMetrics?.totalThreads &&
            corpus.engagementMetrics.totalThreads > 0
              ? "Active discussion"
              : undefined;

          return (
            <CollectionCard
              key={corpus.id}
              type={collectionType}
              badge={firstCategory?.name || "General"}
              image={corpus.icon || undefined}
              imageAlt={corpus.title || "Corpus icon"}
              status={status}
              title={corpus.title || "Untitled Collection"}
              description={corpus.descriptionPreview || corpus.description}
              stats={stats}
              onClick={() => handleCorpusClick(corpus)}
            />
          );
        })}
      </CollectionList>
    </Container>
  );
};
