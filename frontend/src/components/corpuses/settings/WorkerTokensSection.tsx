/**
 * WorkerTokensSection - Manages worker access tokens for a corpus.
 *
 * Displays existing tokens in a table with status, expiry, rate limit, and
 * upload stats.  Both superusers and corpus creators can create, view, and
 * revoke tokens.
 */
import React, { useMemo, useState } from "react";
import { gql, useQuery, useMutation } from "@apollo/client";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  Dropdown as OsDropdown,
  Table,
} from "@os-legal/ui";
import type { DropdownOption } from "@os-legal/ui";
import { Copy, Check, Key, Plus } from "lucide-react";
import { toast } from "react-toastify";
import styled from "styled-components";

import {
  SettingsCard,
  SettingsCardHeader,
  SettingsCardTitle,
  SettingsCardContent,
  InfoNote,
} from "../styles/corpusSettingsStyles";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  OS_LEGAL_SPACING,
} from "../../../assets/configurations/osLegalStyles";
import { getNumericIdFromGlobalId } from "../../../utils/idValidation";
import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";

// ---------------------------------------------------------------------------
// GraphQL operations
// ---------------------------------------------------------------------------

const GET_CORPUS_ACCESS_TOKENS = gql`
  query GetCorpusAccessTokens($corpusId: Int!) {
    corpusAccessTokens(corpusId: $corpusId) {
      id
      keyPrefix
      workerAccountId
      workerAccountName
      isActive
      expiresAt
      rateLimitPerMinute
      created
      uploadCountPending
      uploadCountCompleted
      uploadCountFailed
    }
  }
`;

const GET_WORKER_ACCOUNTS_FOR_TOKENS = gql`
  query GetWorkerAccountsForTokens {
    workerAccounts(isActive: true) {
      id
      name
    }
  }
`;

const CREATE_CORPUS_ACCESS_TOKEN = gql`
  mutation CreateCorpusAccessToken(
    $workerAccountId: Int!
    $corpusId: Int!
    $expiresAt: DateTime
    $rateLimitPerMinute: Int
  ) {
    createCorpusAccessToken(
      workerAccountId: $workerAccountId
      corpusId: $corpusId
      expiresAt: $expiresAt
      rateLimitPerMinute: $rateLimitPerMinute
    ) {
      ok
      token {
        id
        key
        workerAccountName
        corpusId
        expiresAt
        rateLimitPerMinute
        created
      }
    }
  }
`;

const REVOKE_CORPUS_ACCESS_TOKEN = gql`
  mutation RevokeCorpusAccessToken($tokenId: Int!) {
    revokeCorpusAccessToken(tokenId: $tokenId) {
      ok
    }
  }
`;

// ---------------------------------------------------------------------------
// Styled helpers
// ---------------------------------------------------------------------------

const TokenStatusBadge = styled.span<{
  $variant: "active" | "revoked" | "expired";
}>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  border-radius: 9999px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  font-weight: 600;
  background: ${({ $variant }) =>
    $variant === "active"
      ? OS_LEGAL_COLORS.successLight
      : $variant === "revoked"
      ? OS_LEGAL_COLORS.dangerLight
      : OS_LEGAL_COLORS.surfaceHover};
  color: ${({ $variant }) =>
    $variant === "active"
      ? OS_LEGAL_COLORS.success
      : $variant === "revoked"
      ? OS_LEGAL_COLORS.danger
      : OS_LEGAL_COLORS.textMuted};
`;

const MonoText = styled.span`
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  font-size: 0.875rem;
`;

const KeyDisplayContainer = styled.div`
  display: flex;
  gap: 0.5rem;
  align-items: stretch;
  margin-top: 0.75rem;
`;

const KeyInput = styled.input`
  flex: 1;
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  font-size: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  background: ${OS_LEGAL_COLORS.surfaceHover};
  color: ${OS_LEGAL_COLORS.textPrimary};
  outline: none;

  &:focus {
    border-color: ${OS_LEGAL_COLORS.accent};
    box-shadow: 0 0 0 3px ${OS_LEGAL_COLORS.accentLight};
  }
`;

const WarningBox = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: ${OS_LEGAL_COLORS.dangerSurface};
  border: 1px solid ${OS_LEGAL_COLORS.dangerBorder};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.dangerText};
  line-height: 1.5;
`;

const UploadStats = styled.div`
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
`;

const StatChip = styled.span<{ $variant: "pending" | "completed" | "failed" }>`
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  font-weight: 500;
  background: ${({ $variant }) =>
    $variant === "completed"
      ? OS_LEGAL_COLORS.successLight
      : $variant === "failed"
      ? OS_LEGAL_COLORS.dangerLight
      : OS_LEGAL_COLORS.accentLight};
  color: ${({ $variant }) =>
    $variant === "completed"
      ? OS_LEGAL_COLORS.success
      : $variant === "failed"
      ? OS_LEGAL_COLORS.danger
      : OS_LEGAL_COLORS.accent};
`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CorpusAccessToken {
  id: number;
  keyPrefix: string;
  workerAccountId: number;
  workerAccountName: string;
  isActive: boolean;
  expiresAt: string | null;
  rateLimitPerMinute: number;
  created: string;
  uploadCountPending: number;
  uploadCountCompleted: number;
  uploadCountFailed: number;
}

interface WorkerAccountOption {
  id: number;
  name: string;
}

interface WorkerTokensSectionProps {
  corpusId: string; // Relay global ID from corpus
  isSuperuser: boolean;
  isCreator: boolean;
}

interface CreateFormState {
  workerAccountId: number | null;
  expiresAt: string;
  rateLimitPerMinute: number;
}

const initialFormState: CreateFormState = {
  workerAccountId: null,
  expiresAt: "",
  rateLimitPerMinute: 0,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const WorkerTokensSection: React.FC<WorkerTokensSectionProps> = ({
  corpusId,
  isSuperuser,
  isCreator,
}) => {
  const numericCorpusId = useMemo(() => {
    try {
      return getNumericIdFromGlobalId(corpusId);
    } catch {
      return null;
    }
  }, [corpusId]);

  // UI state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [newTokenKey, setNewTokenKey] = useState("");
  const [copied, setCopied] = useState(false);
  const [formState, setFormState] = useState<CreateFormState>(initialFormState);
  const [tokenToRevoke, setTokenToRevoke] = useState<number | null>(null);

  // Queries
  const {
    data: tokensData,
    loading: loadingTokens,
    error: tokensError,
    refetch: refetchTokens,
  } = useQuery(GET_CORPUS_ACCESS_TOKENS, {
    variables: { corpusId: numericCorpusId! },
    skip: numericCorpusId === null,
    fetchPolicy: "network-only",
  });

  const { data: accountsData, loading: loadingAccounts } = useQuery(
    GET_WORKER_ACCOUNTS_FOR_TOKENS,
    {
      skip: !isSuperuser && !isCreator,
    }
  );

  // Mutations
  const [createToken, { loading: creating }] = useMutation(
    CREATE_CORPUS_ACCESS_TOKEN,
    {
      onCompleted: (result) => {
        if (result.createCorpusAccessToken.ok) {
          const key = result.createCorpusAccessToken.token.key;
          setNewTokenKey(key);
          setShowCreateModal(false);
          setFormState(initialFormState);
          setShowKeyModal(true);
          refetchTokens();
        } else {
          toast.error("Failed to create access token");
        }
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const [revokeToken] = useMutation(REVOKE_CORPUS_ACCESS_TOKEN, {
    onCompleted: (result) => {
      if (result.revokeCorpusAccessToken.ok) {
        toast.success("Token revoked");
        refetchTokens();
      } else {
        toast.error("Failed to revoke token");
      }
    },
    onError: (err) => toast.error(err.message),
  });

  // Handlers
  const handleCreate = () => {
    const variables: Record<string, unknown> = {
      workerAccountId: formState.workerAccountId,
      corpusId: numericCorpusId,
    };
    if (formState.expiresAt) {
      variables.expiresAt = formState.expiresAt;
    }
    if (formState.rateLimitPerMinute > 0) {
      variables.rateLimitPerMinute = formState.rateLimitPerMinute;
    }
    createToken({ variables });
  };

  const handleRevoke = (tokenId: number) => {
    revokeToken({ variables: { tokenId } });
    setTokenToRevoke(null);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(newTokenKey);
      setCopied(true);
      toast.success("Token copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.info("Please select the token text and copy manually (Ctrl+C)");
    }
  };

  const getTokenStatus = (
    token: CorpusAccessToken
  ): "active" | "revoked" | "expired" => {
    if (!token.isActive) return "revoked";
    if (token.expiresAt && new Date(token.expiresAt) < new Date())
      return "expired";
    return "active";
  };

  const formatExpiry = (expiresAt: string | null): string => {
    if (!expiresAt) return "Never";
    return new Date(expiresAt).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const formatRateLimit = (limit: number): string => {
    if (!limit || limit === 0) return "Unlimited";
    return `${limit}/min`;
  };

  // Data
  const tokens: CorpusAccessToken[] = tokensData?.corpusAccessTokens ?? [];
  const workerAccounts: WorkerAccountOption[] =
    accountsData?.workerAccounts ?? [];
  const accountOptions: DropdownOption[] = workerAccounts.map((a) => ({
    value: String(a.id),
    label: a.name,
  }));

  if (numericCorpusId === null) {
    return (
      <ErrorMessage title="Invalid corpus ID">
        Unable to parse the corpus identifier.
      </ErrorMessage>
    );
  }

  return (
    <>
      <SettingsCard>
        <SettingsCardHeader>
          <SettingsCardTitle>
            <Key size={18} style={{ marginRight: "-0.25rem" }} />
            Worker Access Tokens
          </SettingsCardTitle>
          {(isSuperuser || isCreator) && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowCreateModal(true)}
              leftIcon={<Plus size={14} />}
            >
              Create Token
            </Button>
          )}
        </SettingsCardHeader>

        <SettingsCardContent>
          <InfoNote>
            Access tokens allow <strong>worker accounts</strong> to upload
            documents to this corpus via the REST API. Each token is{" "}
            <span className="highlight">scoped to a single corpus</span> and can
            be rate-limited or set to expire.
          </InfoNote>

          {loadingTokens && <LoadingState message="Loading tokens..." />}

          {tokensError && (
            <ErrorMessage title="Error loading tokens">
              {tokensError.message}
            </ErrorMessage>
          )}

          {!loadingTokens && !tokensError && tokens.length === 0 && (
            <InfoMessage title="No Access Tokens">
              {isSuperuser || isCreator
                ? "Create a token to allow a worker account to upload documents to this corpus."
                : "No access tokens have been created for this corpus yet. Contact an administrator to create one."}
            </InfoMessage>
          )}

          {!loadingTokens && !tokensError && tokens.length > 0 && (
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Key Prefix</Table.HeadCell>
                  <Table.HeadCell>Worker Account</Table.HeadCell>
                  <Table.HeadCell>Status</Table.HeadCell>
                  <Table.HeadCell>Expiry</Table.HeadCell>
                  <Table.HeadCell>Rate Limit</Table.HeadCell>
                  <Table.HeadCell>Uploads</Table.HeadCell>
                  <Table.HeadCell>Actions</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {tokens.map((token) => {
                  const status = getTokenStatus(token);
                  return (
                    <Table.Row key={token.id}>
                      <Table.Cell>
                        <MonoText>{token.keyPrefix}...</MonoText>
                      </Table.Cell>
                      <Table.Cell>{token.workerAccountName}</Table.Cell>
                      <Table.Cell>
                        <TokenStatusBadge $variant={status}>
                          {status === "active"
                            ? "Active"
                            : status === "revoked"
                            ? "Revoked"
                            : "Expired"}
                        </TokenStatusBadge>
                      </Table.Cell>
                      <Table.Cell>{formatExpiry(token.expiresAt)}</Table.Cell>
                      <Table.Cell>
                        {formatRateLimit(token.rateLimitPerMinute)}
                      </Table.Cell>
                      <Table.Cell>
                        <UploadStats>
                          {token.uploadCountCompleted > 0 && (
                            <StatChip $variant="completed">
                              {token.uploadCountCompleted} done
                            </StatChip>
                          )}
                          {token.uploadCountPending > 0 && (
                            <StatChip $variant="pending">
                              {token.uploadCountPending} pending
                            </StatChip>
                          )}
                          {token.uploadCountFailed > 0 && (
                            <StatChip $variant="failed">
                              {token.uploadCountFailed} failed
                            </StatChip>
                          )}
                          {token.uploadCountCompleted === 0 &&
                            token.uploadCountPending === 0 &&
                            token.uploadCountFailed === 0 && (
                              <span
                                style={{
                                  color: OS_LEGAL_COLORS.textMuted,
                                  fontSize: "0.875rem",
                                }}
                              >
                                None
                              </span>
                            )}
                        </UploadStats>
                      </Table.Cell>
                      <Table.Cell>
                        {status === "active" && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setTokenToRevoke(token.id)}
                            style={{ color: OS_LEGAL_COLORS.danger }}
                          >
                            Revoke
                          </Button>
                        )}
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table>
          )}
        </SettingsCardContent>
      </SettingsCard>

      {/* Create Token Modal */}
      <Modal open={showCreateModal} onClose={() => setShowCreateModal(false)}>
        <ModalHeader>Create Access Token</ModalHeader>
        <ModalBody>
          {loadingAccounts ? (
            <LoadingState message="Loading worker accounts..." />
          ) : (
            <div
              style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    fontWeight: 600,
                    fontSize: "0.875rem",
                    marginBottom: "0.375rem",
                  }}
                >
                  Worker Account *
                </label>
                <OsDropdown
                  mode="select"
                  placeholder="Select a worker account"
                  options={accountOptions}
                  value={
                    formState.workerAccountId != null
                      ? String(formState.workerAccountId)
                      : null
                  }
                  onChange={(val) =>
                    setFormState({
                      ...formState,
                      workerAccountId:
                        typeof val === "string" ? parseInt(val, 10) : null,
                    })
                  }
                />
              </div>
              <Input
                label="Expiry Date (optional)"
                type="datetime-local"
                fullWidth
                value={formState.expiresAt}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, expiresAt: e.target.value })
                }
              />
              <Input
                label="Rate Limit (requests/min, 0 = unlimited)"
                type="number"
                fullWidth
                value={formState.rateLimitPerMinute}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({
                    ...formState,
                    rateLimitPerMinute: parseInt(e.target.value, 10) || 0,
                  })
                }
              />
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={creating}
            disabled={!formState.workerAccountId || creating}
            onClick={handleCreate}
          >
            Create Token
          </Button>
        </ModalFooter>
      </Modal>

      {/* One-Time Key Display Modal — block outside-click so users must explicitly close */}
      <Modal
        open={showKeyModal}
        onClose={() => {
          setShowKeyModal(false);
          setNewTokenKey("");
          setCopied(false);
        }}
        closeOnOverlay={false}
        closeOnEscape={false}
      >
        <ModalHeader>Access Token Created</ModalHeader>
        <ModalBody>
          <WarningBox>
            <Key size={20} style={{ flexShrink: 0, marginTop: "0.125rem" }} />
            <span>
              This key will only be shown <strong>once</strong>. Copy it now and
              store it securely. You will not be able to retrieve it later.
            </span>
          </WarningBox>
          <KeyDisplayContainer>
            <KeyInput
              readOnly
              value={newTokenKey}
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <Button
              variant={copied ? "primary" : "secondary"}
              onClick={handleCopy}
              style={{ height: "auto" }}
            >
              {copied ? <Check size={18} /> : <Copy size={18} />}
            </Button>
          </KeyDisplayContainer>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => {
              setShowKeyModal(false);
              setNewTokenKey("");
              setCopied(false);
            }}
          >
            Close
          </Button>
        </ModalFooter>
      </Modal>

      {/* Revoke Confirmation */}
      <Modal
        open={tokenToRevoke !== null}
        onClose={() => setTokenToRevoke(null)}
      >
        <ModalHeader>Confirm Revoke</ModalHeader>
        <ModalBody>
          Are you sure you want to revoke this token? This cannot be undone.
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setTokenToRevoke(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() =>
              tokenToRevoke !== null && handleRevoke(tokenToRevoke)
            }
          >
            Revoke
          </Button>
        </ModalFooter>
      </Modal>
    </>
  );
};
