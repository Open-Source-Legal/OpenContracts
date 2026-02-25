import React, { useState } from "react";
import { useQuery, useMutation } from "@apollo/client";
import {
  Button,
  Table,
  Message,
  Icon,
  Modal,
  Form,
  Input,
  Dropdown,
  Loader,
  Label,
} from "semantic-ui-react";
import { toast } from "react-toastify";
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  OS_LEGAL_SPACING,
} from "../../../assets/configurations/osLegalStyles";
import {
  GET_CORPUS_ACCESS_TOKENS,
  GetCorpusAccessTokensInput,
  GetCorpusAccessTokensOutput,
  CorpusAccessTokenData,
  GET_WORKER_ACCOUNTS,
  GetWorkerAccountsOutput,
  CREATE_CORPUS_ACCESS_TOKEN,
  CreateCorpusAccessTokenInput,
  CreateCorpusAccessTokenOutput,
  REVOKE_CORPUS_ACCESS_TOKEN,
  RevokeCorpusAccessTokenInput,
  RevokeCorpusAccessTokenOutput,
} from "../../../graphql/queries/workerQueries";

// ============================================================================
// Styled Components
// ============================================================================

const TokenKeyDisplay = styled.div`
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  padding: 1rem;
  margin-top: 1rem;
  font-family: monospace;
  word-break: break-all;
  position: relative;
`;

const TokenKeyLabel = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.danger};
  font-weight: 700;
  margin-bottom: 0.5rem;
`;

const TokenKeyValue = styled.code`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: block;
  padding: 0.5rem;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 4px;
`;

const StatusBadge = styled(Label)<{ $active: boolean }>`
  &.ui.label {
    background: ${(props) => (props.$active ? "#dcfce7" : "#fef3c7")};
    color: ${(props) => (props.$active ? "#166534" : "#92400e")};
    font-weight: 500;
    font-size: 0.75rem;
  }
`;

const UploadCountBadge = styled(Label)`
  &.ui.label {
    background: #f1f5f9;
    color: #475569;
    font-weight: 500;
    font-size: 0.75rem;
  }
`;

const InfoBanner = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: rgba(14, 165, 233, 0.08);
  border: 1px solid rgba(14, 165, 233, 0.2);
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  margin-bottom: 1rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  color: #0c4a6e;
  line-height: 1.5;
`;

// ============================================================================
// Component
// ============================================================================

interface WorkerAccessTokensSectionProps {
  corpusId: string;
  isSuperuser: boolean;
  isOwner: boolean;
}

export const WorkerAccessTokensSection: React.FC<
  WorkerAccessTokensSectionProps
> = ({ corpusId, isSuperuser, isOwner }) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [createdTokenKey, setCreatedTokenKey] = useState("");
  const [selectedWorkerId, setSelectedWorkerId] = useState<number | null>(null);
  const [expiresInDays, setExpiresInDays] = useState<string>("");
  const [rateLimit, setRateLimit] = useState<string>("0");

  // Parse numeric corpus ID from the relay-style global ID
  const numericCorpusId = parseInt(
    corpusId.includes(":")
      ? atob(corpusId).split(":")[1]
      : corpusId.replace(/\D/g, ""),
    10
  );

  const {
    data: tokensData,
    loading: tokensLoading,
    refetch: refetchTokens,
  } = useQuery<GetCorpusAccessTokensOutput, GetCorpusAccessTokensInput>(
    GET_CORPUS_ACCESS_TOKENS,
    {
      variables: { corpusId: numericCorpusId },
      skip: !numericCorpusId,
      fetchPolicy: "network-only",
    }
  );

  const { data: accountsData } = useQuery<GetWorkerAccountsOutput>(
    GET_WORKER_ACCOUNTS,
    { skip: !isSuperuser }
  );

  const [createToken, { loading: creatingToken }] = useMutation<
    CreateCorpusAccessTokenOutput,
    CreateCorpusAccessTokenInput
  >(CREATE_CORPUS_ACCESS_TOKEN, {
    onCompleted: (data) => {
      if (data.createCorpusAccessToken.ok) {
        setCreatedTokenKey(data.createCorpusAccessToken.token.key);
        setShowCreateModal(false);
        setShowTokenModal(true);
        resetForm();
        refetchTokens();
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const [revokeToken] = useMutation<
    RevokeCorpusAccessTokenOutput,
    RevokeCorpusAccessTokenInput
  >(REVOKE_CORPUS_ACCESS_TOKEN, {
    onCompleted: (data) => {
      if (data.revokeCorpusAccessToken.ok) {
        toast.success("Token revoked");
        refetchTokens();
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const resetForm = () => {
    setSelectedWorkerId(null);
    setExpiresInDays("");
    setRateLimit("0");
  };

  const handleCreate = () => {
    if (!selectedWorkerId) {
      toast.error("Select a worker account");
      return;
    }

    let expiresAt: string | undefined;
    if (expiresInDays && parseInt(expiresInDays, 10) > 0) {
      const date = new Date();
      date.setDate(date.getDate() + parseInt(expiresInDays, 10));
      expiresAt = date.toISOString();
    }

    createToken({
      variables: {
        workerAccountId: selectedWorkerId,
        corpusId: numericCorpusId,
        expiresAt,
        rateLimitPerMinute: parseInt(rateLimit, 10) || 0,
      },
    });
  };

  const handleCopyToken = () => {
    navigator.clipboard.writeText(createdTokenKey).then(
      () => toast.success("Token copied to clipboard"),
      () => toast.error("Failed to copy token")
    );
  };

  const tokens: CorpusAccessTokenData[] = tokensData?.corpusAccessTokens || [];
  const workerAccounts = accountsData?.workerAccounts || [];
  const activeWorkerAccounts = workerAccounts.filter((a) => a.isActive);

  const workerOptions = activeWorkerAccounts.map((a) => ({
    key: a.id,
    value: a.id,
    text: a.name,
  }));

  if (!isSuperuser && !isOwner) {
    return null;
  }

  return (
    <>
      <InfoBanner>
        <Icon name="info circle" style={{ color: "#0284c7", flexShrink: 0 }} />
        <span>
          Worker access tokens allow external document processing workers to
          upload pre-processed documents directly to this corpus. Tokens are
          scoped to this corpus only.
        </span>
      </InfoBanner>

      {tokensLoading ? (
        <Loader active inline="centered" />
      ) : tokens.length === 0 ? (
        <Message info>
          <Message.Header>No Access Tokens</Message.Header>
          <p>
            No worker access tokens have been created for this corpus yet.
            {isSuperuser && " Click the button below to create one."}
          </p>
        </Message>
      ) : (
        <Table basic="very" striped compact size="small">
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>Key Prefix</Table.HeaderCell>
              <Table.HeaderCell>Worker</Table.HeaderCell>
              <Table.HeaderCell>Status</Table.HeaderCell>
              <Table.HeaderCell>Expires</Table.HeaderCell>
              <Table.HeaderCell>Rate Limit</Table.HeaderCell>
              <Table.HeaderCell>Uploads</Table.HeaderCell>
              <Table.HeaderCell>Created</Table.HeaderCell>
              {isSuperuser && (
                <Table.HeaderCell textAlign="right">Actions</Table.HeaderCell>
              )}
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {tokens.map((token) => (
              <Table.Row key={token.id}>
                <Table.Cell>
                  <code>{token.keyPrefix}...</code>
                </Table.Cell>
                <Table.Cell>{token.workerAccountName}</Table.Cell>
                <Table.Cell>
                  <StatusBadge $active={token.isActive}>
                    {token.isActive ? "Active" : "Revoked"}
                  </StatusBadge>
                </Table.Cell>
                <Table.Cell>
                  {token.expiresAt
                    ? new Date(token.expiresAt).toLocaleDateString()
                    : "Never"}
                </Table.Cell>
                <Table.Cell>
                  {token.rateLimitPerMinute > 0
                    ? `${token.rateLimitPerMinute}/min`
                    : "Unlimited"}
                </Table.Cell>
                <Table.Cell>
                  <UploadCountBadge>
                    <Icon name="upload" />
                    {token.uploadCount}
                  </UploadCountBadge>
                </Table.Cell>
                <Table.Cell>
                  {new Date(token.created).toLocaleDateString()}
                </Table.Cell>
                {isSuperuser && (
                  <Table.Cell textAlign="right">
                    {token.isActive && (
                      <Button
                        size="mini"
                        color="orange"
                        icon
                        labelPosition="left"
                        onClick={() =>
                          revokeToken({
                            variables: { tokenId: token.id },
                          })
                        }
                      >
                        <Icon name="ban" />
                        Revoke
                      </Button>
                    )}
                  </Table.Cell>
                )}
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      )}

      {isSuperuser && (
        <div style={{ marginTop: "1rem" }}>
          <Button
            primary
            icon
            labelPosition="left"
            size="small"
            onClick={() => {
              resetForm();
              setShowCreateModal(true);
            }}
          >
            <Icon name="plus" />
            Create Access Token
          </Button>
        </div>
      )}

      {/* Create Token Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        size="small"
      >
        <Modal.Header>
          <Icon name="key" /> Create Corpus Access Token
        </Modal.Header>
        <Modal.Content>
          <Form>
            <Form.Field required>
              <label>Worker Account</label>
              <Dropdown
                placeholder="Select a worker account"
                fluid
                selection
                options={workerOptions}
                value={selectedWorkerId || ""}
                onChange={(_, d) => setSelectedWorkerId(d.value as number)}
              />
            </Form.Field>
            <Form.Field>
              <label>Expires In (days)</label>
              <Input
                type="number"
                min="0"
                placeholder="Leave empty for no expiration"
                value={expiresInDays}
                onChange={(_, d) => setExpiresInDays(d.value)}
              />
            </Form.Field>
            <Form.Field>
              <label>Rate Limit (requests per minute)</label>
              <Input
                type="number"
                min="0"
                placeholder="0 = unlimited"
                value={rateLimit}
                onChange={(_, d) => setRateLimit(d.value)}
              />
            </Form.Field>
          </Form>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
          <Button
            primary
            loading={creatingToken}
            disabled={!selectedWorkerId || creatingToken}
            onClick={handleCreate}
          >
            Create Token
          </Button>
        </Modal.Actions>
      </Modal>

      {/* Token Display Modal (one-time display) */}
      <Modal
        open={showTokenModal}
        onClose={() => {
          setShowTokenModal(false);
          setCreatedTokenKey("");
        }}
        size="small"
        closeOnDimmerClick={false}
      >
        <Modal.Header>
          <Icon name="warning sign" color="orange" /> Save Your Access Token
        </Modal.Header>
        <Modal.Content>
          <Message warning>
            <Message.Header>This token will only be shown once</Message.Header>
            <p>
              Copy and securely store this token now. After closing this dialog,
              you will not be able to see the full token again.
            </p>
          </Message>
          <TokenKeyDisplay>
            <TokenKeyLabel>Access Token</TokenKeyLabel>
            <TokenKeyValue>{createdTokenKey}</TokenKeyValue>
          </TokenKeyDisplay>
          <div style={{ marginTop: "1rem" }}>
            <strong>Usage:</strong>
            <pre
              style={{
                background: "#f8fafc",
                padding: "0.75rem",
                borderRadius: "4px",
                fontSize: "0.8rem",
                overflow: "auto",
              }}
            >
              {`Authorization: WorkerKey ${createdTokenKey.substring(0, 8)}...`}
            </pre>
          </div>
        </Modal.Content>
        <Modal.Actions>
          <Button primary icon labelPosition="left" onClick={handleCopyToken}>
            <Icon name="copy" />
            Copy Token
          </Button>
          <Button
            onClick={() => {
              setShowTokenModal(false);
              setCreatedTokenKey("");
            }}
          >
            Done
          </Button>
        </Modal.Actions>
      </Modal>
    </>
  );
};
