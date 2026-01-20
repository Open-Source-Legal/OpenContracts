import React, { useState, useCallback } from "react";
import { useQuery, useMutation } from "@apollo/client";
import {
  Segment,
  Header,
  Icon,
  Table,
  Dropdown,
  Button,
  Modal,
  Form,
  Message,
  Label,
  Loader,
  Dimmer,
  Grid,
} from "semantic-ui-react";
import { Checkbox, StatBlock } from "@os-legal/ui";
import { toast } from "react-toastify";
import { formatDistanceToNow, format } from "date-fns";

import {
  GET_MODERATION_ACTIONS,
  GET_MODERATION_METRICS,
  GetModerationActionsInput,
  GetModerationActionsOutput,
  GetModerationMetricsInput,
  GetModerationMetricsOutput,
  ModerationActionNode,
} from "../../graphql/queries";
import {
  ROLLBACK_MODERATION_ACTION,
  RollbackModerationActionInput,
  RollbackModerationActionOutput,
} from "../../graphql/mutations";

/** Page size for moderation actions list */
const MODERATION_PAGE_SIZE = 10;

/** Moderation action type enum for type safety */
export enum ModerationActionTypeEnum {
  LOCK_THREAD = "lock_thread",
  UNLOCK_THREAD = "unlock_thread",
  PIN_THREAD = "pin_thread",
  UNPIN_THREAD = "unpin_thread",
  DELETE_MESSAGE = "delete_message",
  RESTORE_MESSAGE = "restore_message",
  DELETE_THREAD = "delete_thread",
  RESTORE_THREAD = "restore_thread",
}

interface ModerationDashboardProps {
  corpusId: string;
  corpusTitle?: string;
}

const ACTION_TYPE_OPTIONS = [
  { key: "all", value: "", text: "All Actions" },
  {
    key: ModerationActionTypeEnum.LOCK_THREAD,
    value: ModerationActionTypeEnum.LOCK_THREAD,
    text: "Lock Thread",
  },
  {
    key: ModerationActionTypeEnum.UNLOCK_THREAD,
    value: ModerationActionTypeEnum.UNLOCK_THREAD,
    text: "Unlock Thread",
  },
  {
    key: ModerationActionTypeEnum.PIN_THREAD,
    value: ModerationActionTypeEnum.PIN_THREAD,
    text: "Pin Thread",
  },
  {
    key: ModerationActionTypeEnum.UNPIN_THREAD,
    value: ModerationActionTypeEnum.UNPIN_THREAD,
    text: "Unpin Thread",
  },
  {
    key: ModerationActionTypeEnum.DELETE_MESSAGE,
    value: ModerationActionTypeEnum.DELETE_MESSAGE,
    text: "Delete Message",
  },
  {
    key: ModerationActionTypeEnum.RESTORE_MESSAGE,
    value: ModerationActionTypeEnum.RESTORE_MESSAGE,
    text: "Restore Message",
  },
  {
    key: ModerationActionTypeEnum.DELETE_THREAD,
    value: ModerationActionTypeEnum.DELETE_THREAD,
    text: "Delete Thread",
  },
  {
    key: ModerationActionTypeEnum.RESTORE_THREAD,
    value: ModerationActionTypeEnum.RESTORE_THREAD,
    text: "Restore Thread",
  },
];

const TIME_RANGE_OPTIONS = [
  { key: "1h", value: 1, text: "Last hour" },
  { key: "24h", value: 24, text: "Last 24 hours" },
  { key: "7d", value: 168, text: "Last 7 days" },
  { key: "30d", value: 720, text: "Last 30 days" },
];

const formatActionType = (actionType: string): string => {
  return actionType
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};

const getActionColor = (
  actionType: string
): "red" | "green" | "blue" | "yellow" | "grey" => {
  if (actionType.includes("delete")) return "red";
  if (actionType.includes("restore")) return "green";
  if (actionType.includes("lock")) return "yellow";
  if (actionType.includes("pin")) return "blue";
  return "grey";
};

export const ModerationDashboard: React.FC<ModerationDashboardProps> = ({
  corpusId,
  corpusTitle,
}) => {
  const [selectedActionType, setSelectedActionType] = useState<string>("");
  const [automatedOnly, setAutomatedOnly] = useState<boolean>(false);
  const [timeRangeHours, setTimeRangeHours] = useState<number>(24);
  const [rollbackModalOpen, setRollbackModalOpen] = useState<boolean>(false);
  const [selectedAction, setSelectedAction] =
    useState<ModerationActionNode | null>(null);
  const [rollbackReason, setRollbackReason] = useState<string>("");
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);

  // Query moderation actions
  const {
    data: actionsData,
    loading: actionsLoading,
    error: actionsError,
    refetch: refetchActions,
    fetchMore,
  } = useQuery<GetModerationActionsOutput, GetModerationActionsInput>(
    GET_MODERATION_ACTIONS,
    {
      variables: {
        corpusId,
        actionTypes: selectedActionType ? [selectedActionType] : undefined,
        automatedOnly: automatedOnly || undefined,
        first: MODERATION_PAGE_SIZE,
      },
      fetchPolicy: "cache-and-network",
    }
  );

  // Handle loading more actions with cursor-based pagination
  const handleLoadMore = useCallback(async () => {
    const endCursor = actionsData?.moderationActions?.pageInfo?.endCursor;
    if (!endCursor || isLoadingMore) return;

    setIsLoadingMore(true);
    try {
      await fetchMore({
        variables: {
          after: endCursor,
          first: MODERATION_PAGE_SIZE,
        },
        updateQuery: (prev, { fetchMoreResult }) => {
          if (!fetchMoreResult) return prev;

          return {
            ...fetchMoreResult,
            moderationActions: {
              ...fetchMoreResult.moderationActions,
              edges: [
                ...(prev.moderationActions?.edges || []),
                ...(fetchMoreResult.moderationActions?.edges || []),
              ],
            },
          };
        },
      });
    } catch (error) {
      toast.error("Failed to load more actions");
    } finally {
      setIsLoadingMore(false);
    }
  }, [actionsData, fetchMore, isLoadingMore]);

  // Query moderation metrics
  const {
    data: metricsData,
    loading: metricsLoading,
    error: metricsError,
  } = useQuery<GetModerationMetricsOutput, GetModerationMetricsInput>(
    GET_MODERATION_METRICS,
    {
      variables: {
        corpusId,
        timeRangeHours,
      },
      fetchPolicy: "cache-and-network",
    }
  );

  // Rollback mutation
  const [rollbackAction, { loading: rollbackLoading }] = useMutation<
    RollbackModerationActionOutput,
    RollbackModerationActionInput
  >(ROLLBACK_MODERATION_ACTION, {
    onCompleted: (data) => {
      if (data.rollbackModerationAction.ok) {
        toast.success(data.rollbackModerationAction.message);
        setRollbackModalOpen(false);
        setSelectedAction(null);
        setRollbackReason("");
        refetchActions();
      } else {
        toast.error(data.rollbackModerationAction.message);
      }
    },
    onError: (error) => {
      toast.error(`Failed to rollback: ${error.message}`);
    },
  });

  const handleRollback = () => {
    if (!selectedAction) return;
    rollbackAction({
      variables: {
        actionId: selectedAction.id,
        reason: rollbackReason || undefined,
      },
    });
  };

  const openRollbackModal = (action: ModerationActionNode) => {
    setSelectedAction(action);
    setRollbackModalOpen(true);
  };

  const metrics = metricsData?.moderationMetrics;
  const actions = actionsData?.moderationActions?.edges || [];

  return (
    <div style={{ padding: "1rem" }}>
      <Header as="h2" dividing>
        <Icon name="shield" />
        <Header.Content>
          Moderation Dashboard
          {corpusTitle && <Header.Subheader>{corpusTitle}</Header.Subheader>}
        </Header.Content>
      </Header>

      {/* Metrics Section */}
      <Segment>
        <Header as="h4">
          <Icon name="chart bar" />
          Moderation Metrics
          <Dropdown
            inline
            options={TIME_RANGE_OPTIONS}
            value={timeRangeHours}
            onChange={(_, { value }) => setTimeRangeHours(value as number)}
            style={{ marginLeft: "1rem" }}
          />
        </Header>
        {metricsLoading ? (
          <Loader active inline="centered" />
        ) : metricsError ? (
          <Message negative>
            <Message.Header>Error loading metrics</Message.Header>
            <p>{metricsError.message}</p>
          </Message>
        ) : metrics ? (
          <>
            {metrics.isAboveThreshold && (
              <Message warning>
                <Icon name="warning sign" />
                High moderation activity detected! Threshold exceeded for:{" "}
                {metrics.thresholdExceededTypes.join(", ")}
              </Message>
            )}
            <Grid columns={4} stackable>
              <Grid.Column>
                <StatBlock
                  value={metrics.totalActions}
                  label="Total Actions"
                  size="sm"
                />
              </Grid.Column>
              <Grid.Column>
                <StatBlock
                  value={metrics.automatedActions}
                  label="Automated"
                  size="sm"
                  variant="accent"
                />
              </Grid.Column>
              <Grid.Column>
                <StatBlock
                  value={metrics.manualActions}
                  label="Manual"
                  size="sm"
                  variant="accent"
                />
              </Grid.Column>
              <Grid.Column>
                <StatBlock
                  value={metrics.hourlyActionRate.toFixed(1)}
                  label="Actions/Hour"
                  size="sm"
                />
              </Grid.Column>
            </Grid>
          </>
        ) : (
          <Message info>No metrics available</Message>
        )}
      </Segment>

      {/* Filters */}
      <Segment>
        <Header as="h4">
          <Icon name="filter" />
          Filters
        </Header>
        <Form>
          <Form.Group inline>
            <Form.Field>
              <label>Action Type</label>
              <Dropdown
                selection
                options={ACTION_TYPE_OPTIONS}
                value={selectedActionType}
                onChange={(_, { value }) =>
                  setSelectedActionType(value as string)
                }
              />
            </Form.Field>
            <Form.Field>
              <Checkbox
                label="Automated actions only"
                checked={automatedOnly}
                onChange={(e) => setAutomatedOnly(e.target.checked)}
              />
            </Form.Field>
          </Form.Group>
        </Form>
      </Segment>

      {/* Actions Table */}
      <Segment>
        <Header as="h4">
          <Icon name="list" />
          Moderation Actions
        </Header>
        {actionsLoading ? (
          <Dimmer active inverted>
            <Loader>Loading actions...</Loader>
          </Dimmer>
        ) : actionsError ? (
          <Message negative>
            <Message.Header>Error loading actions</Message.Header>
            <p>{actionsError.message}</p>
          </Message>
        ) : actions.length === 0 ? (
          <Message info>No moderation actions found</Message>
        ) : (
          <>
            <Table celled striped>
              <Table.Header>
                <Table.Row>
                  <Table.HeaderCell>Action</Table.HeaderCell>
                  <Table.HeaderCell>Target</Table.HeaderCell>
                  <Table.HeaderCell>Moderator</Table.HeaderCell>
                  <Table.HeaderCell>Reason</Table.HeaderCell>
                  <Table.HeaderCell>Time</Table.HeaderCell>
                  <Table.HeaderCell>Actions</Table.HeaderCell>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {actions.map(({ node }) => (
                  <Table.Row key={node.id}>
                    <Table.Cell>
                      <Label color={getActionColor(node.actionType)}>
                        {formatActionType(node.actionType)}
                      </Label>
                      {node.isAutomated && (
                        <Label size="tiny" color="purple">
                          <Icon name="cog" />
                          Auto
                        </Label>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {node.conversation && (
                        <div>
                          <Icon name="comments" />
                          {node.conversation.title}
                        </div>
                      )}
                      {node.message && (
                        <div style={{ fontSize: "0.9em", color: "#666" }}>
                          <Icon name="comment" />
                          {node.message.content.substring(0, 50)}...
                        </div>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {node.moderator ? (
                        <span>
                          <Icon name="user" />
                          {node.moderator.username}
                        </span>
                      ) : (
                        <span style={{ color: "#888" }}>
                          <Icon name="cog" />
                          System
                        </span>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {node.reason || (
                        <span style={{ color: "#888" }}>
                          No reason provided
                        </span>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <span title={format(new Date(node.created), "PPpp")}>
                        {formatDistanceToNow(new Date(node.created), {
                          addSuffix: true,
                        })}
                      </span>
                    </Table.Cell>
                    <Table.Cell>
                      {node.canRollback && (
                        <Button
                          size="tiny"
                          color="orange"
                          onClick={() => openRollbackModal(node)}
                        >
                          <Icon name="undo" />
                          Rollback
                        </Button>
                      )}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
            {actionsData?.moderationActions?.pageInfo?.hasNextPage && (
              <div style={{ textAlign: "center", marginTop: "1rem" }}>
                <Button
                  onClick={handleLoadMore}
                  loading={isLoadingMore}
                  disabled={isLoadingMore}
                >
                  <Icon name="plus" />
                  Load More
                </Button>
              </div>
            )}
          </>
        )}
      </Segment>

      {/* Rollback Confirmation Modal */}
      <Modal
        open={rollbackModalOpen}
        onClose={() => setRollbackModalOpen(false)}
        size="small"
      >
        <Modal.Header>
          <Icon name="undo" />
          Confirm Rollback
        </Modal.Header>
        <Modal.Content>
          {selectedAction && (
            <>
              <p>
                Are you sure you want to rollback this{" "}
                <strong>{formatActionType(selectedAction.actionType)}</strong>{" "}
                action?
              </p>
              {selectedAction.conversation && (
                <p>
                  Thread: <strong>{selectedAction.conversation.title}</strong>
                </p>
              )}
              <Form>
                <Form.TextArea
                  label="Reason for rollback (optional)"
                  placeholder="Enter a reason for this rollback..."
                  value={rollbackReason}
                  onChange={(_, { value }) =>
                    setRollbackReason(value as string)
                  }
                />
              </Form>
            </>
          )}
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setRollbackModalOpen(false)}>Cancel</Button>
          <Button
            color="orange"
            onClick={handleRollback}
            loading={rollbackLoading}
            disabled={rollbackLoading}
          >
            <Icon name="undo" />
            Rollback
          </Button>
        </Modal.Actions>
      </Modal>
    </div>
  );
};

export default ModerationDashboard;
