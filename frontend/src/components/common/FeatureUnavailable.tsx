import React from "react";
import { Button } from "@os-legal/ui";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import { FEATURE_FLAGS, FeatureKey } from "../../config/features";
import { GET_MY_CORPUSES, GetMyCorpusesOutput } from "../../graphql/queries";
import { useFeatureAvailability } from "../../hooks/useFeatureAvailability";
import { FolderOpen, Plus } from "lucide-react";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
  min-height: 200px;
  color: #666;
`;

const IconWrapper = styled.div`
  margin-bottom: 1rem;
  opacity: 0.5;
`;

const FeatureName = styled.p`
  font-size: 1.2rem;
  font-weight: 500;
  margin: 0.5rem 0;
  color: #333;
`;

const Message = styled.small`
  display: block;
  margin-bottom: 1rem;
  color: #666;
`;

interface FeatureUnavailableProps {
  feature: FeatureKey;
  documentId: string;
  onAddToCorpus?: () => void;
  className?: string;
}

export const FeatureUnavailable: React.FC<FeatureUnavailableProps> = ({
  feature,
  documentId,
  onAddToCorpus,
  className,
}) => {
  const { getFeatureStatus } = useFeatureAvailability();
  const status = getFeatureStatus(feature);
  const { data: userCorpuses } = useQuery<GetMyCorpusesOutput>(GET_MY_CORPUSES);

  if (status.available) return null;

  const hasEditableCorpuses =
    (userCorpuses?.myCorpuses?.edges?.length || 0) > 0;

  return (
    <Container className={className}>
      <IconWrapper>
        <FolderOpen size={48} />
      </IconWrapper>
      <FeatureName>{status.config.displayName}</FeatureName>
      <Message>{status.message}</Message>

      {hasEditableCorpuses && onAddToCorpus && (
        <Button
          size="sm"
          variant="primary"
          onClick={onAddToCorpus}
          leftIcon={<Plus size={16} />}
        >
          Add to Corpus
        </Button>
      )}
    </Container>
  );
};
