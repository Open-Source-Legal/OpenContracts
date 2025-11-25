import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import {
  Modal,
  Button,
  Form,
  Dropdown,
  Message,
  Icon,
} from "semantic-ui-react";
import {
  AWARD_BADGE,
  AwardBadgeInput,
  AwardBadgeOutput,
} from "../../graphql/mutations";
import {
  GET_BADGES,
  GetBadgesOutput,
  GetBadgesInput,
} from "../../graphql/queries";

interface AwardBadgeModalProps {
  open: boolean;
  onClose: () => void;
  userId: string;
  corpusId?: string;
  onSuccess?: () => void;
}

export const AwardBadgeModal: React.FC<AwardBadgeModalProps> = ({
  open,
  onClose,
  userId,
  corpusId,
  onSuccess,
}) => {
  const [selectedBadgeId, setSelectedBadgeId] = useState<string>("");

  const { loading: loadingBadges, data: badgesData } = useQuery<
    GetBadgesOutput,
    GetBadgesInput
  >(GET_BADGES, {
    variables: {
      corpusId,
      limit: 100,
    },
    skip: !open,
  });

  const [awardBadge, { loading: awarding, error }] = useMutation<
    AwardBadgeOutput,
    AwardBadgeInput
  >(AWARD_BADGE, {
    onCompleted: () => {
      onClose();
      setSelectedBadgeId("");
      if (onSuccess) {
        onSuccess();
      }
    },
  });

  const handleAward = () => {
    if (selectedBadgeId && userId) {
      awardBadge({
        variables: {
          badgeId: selectedBadgeId,
          userId,
          corpusId,
        },
      });
    }
  };

  const badges = badgesData?.badges?.edges?.map((edge) => edge.node) || [];
  const badgeOptions = badges.map((badge) => ({
    key: badge.id,
    text: `${badge.name} (${badge.badgeType})`,
    value: badge.id,
    description: badge.description,
  }));

  return (
    <Modal open={open} onClose={onClose} size="small">
      <Modal.Header>
        <Icon name="trophy" />
        Award Badge
      </Modal.Header>
      <Modal.Content>
        {error && (
          <Message negative>
            <Message.Header>Error awarding badge</Message.Header>
            <p>{error.message}</p>
          </Message>
        )}

        <Form>
          <Form.Field required>
            <label>Select Badge</label>
            <Dropdown
              placeholder="Choose a badge to award"
              fluid
              search
              selection
              loading={loadingBadges}
              options={badgeOptions}
              value={selectedBadgeId}
              onChange={(_, { value }) => setSelectedBadgeId(value as string)}
            />
          </Form.Field>

          {badges.find((b) => b.id === selectedBadgeId) && (
            <Message info>
              <Message.Header>
                {badges.find((b) => b.id === selectedBadgeId)?.name}
              </Message.Header>
              <p>{badges.find((b) => b.id === selectedBadgeId)?.description}</p>
            </Message>
          )}
        </Form>
      </Modal.Content>
      <Modal.Actions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          primary
          onClick={handleAward}
          loading={awarding}
          disabled={!selectedBadgeId || awarding}
          icon
          labelPosition="left"
        >
          <Icon name="trophy" />
          Award Badge
        </Button>
      </Modal.Actions>
    </Modal>
  );
};
