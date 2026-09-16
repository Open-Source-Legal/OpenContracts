import React, { useState } from "react";
import {
  DocumentNode,
  useApolloClient,
  useQuery,
  useReactiveVar,
} from "@apollo/client";
import { Link } from "react-router-dom";
import {
  Button,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";
import styled from "styled-components";
import {
  AUTOMATION_CREDENTIAL_DEFAULT_DAYS,
  AUTOMATION_CREDENTIAL_NAME_MAX_LENGTH,
  TABLET_BREAKPOINT,
} from "../../assets/configurations/constants";
import { backendUserObj } from "../../graphql/cache";
import {
  AutomationCredential,
  GET_AUTOMATION_CREDENTIALS,
  GET_AUTOMATION_CREDENTIAL,
  GET_AUTOMATION_SCOPES,
  GET_AUTOMATION_CHOICES,
  MINT_AUTOMATION_CREDENTIAL,
  ROTATE_AUTOMATION_CREDENTIAL,
  REVOKE_AUTOMATION_CREDENTIAL,
} from "../../graphql/automationCredentials";
import { FormField } from "../widgets/form/FormField";
import { CardSegment, ScrollableTableWrapper } from "../layout/SharedSegments";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
} from "../../assets/configurations/osLegalStyles";

const Container = styled.main`
  max-width: ${OS_LEGAL_SPACING.pageMaxWidth};
  padding: ${OS_LEGAL_SPACING.pagePaddingDesktop};
  margin: auto;
  overflow: auto;
  color: ${OS_LEGAL_COLORS.textPrimary};
  label {
    display: block;
    margin: 0.5rem 0;
  }
  fieldset {
    margin: 1rem 0;
    border: 1px solid ${OS_LEGAL_COLORS.border};
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    text-align: left;
    padding: 0.75rem;
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
  code {
    overflow-wrap: anywhere;
  }
`;

interface Choice {
  id: string;
  label: string;
}
interface ChoicePage {
  items: Choice[];
  totalCount: number;
}

function PageButtons({
  offset,
  count,
  total,
  onChange,
}: {
  offset: number;
  count: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div>
      <Button
        variant="secondary"
        disabled={offset === 0}
        onClick={() => onChange(0)}
      >
        First page
      </Button>
      <span>
        {" "}
        {offset + (count ? 1 : 0)}–{offset + count} of {total}{" "}
      </span>
      <Button
        variant="secondary"
        disabled={!count || offset + count >= total}
        onClick={() => onChange(offset + count)}
      >
        Next page
      </Button>
    </div>
  );
}

function ChoicePicker({
  kind,
  selected,
  onChange,
}: {
  kind: "principal" | "corpus";
  selected: Choice[];
  onChange: (choices: Choice[]) => void;
}) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, loading, error } = useQuery<{
    automationCredentialChoices: ChoicePage;
  }>(GET_AUTOMATION_CHOICES, {
    variables: { kind, search, offset },
    fetchPolicy: "no-cache",
  });
  const page = data?.automationCredentialChoices;
  return (
    <fieldset>
      <legend>
        {kind === "principal" ? "Active principal" : "Allowed corpuses"}
      </legend>
      <Input
        aria-label={`Search ${kind}`}
        placeholder="Search by name or ID"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setOffset(0);
        }}
      />
      {selected.length > 0 && (
        <p>
          Selected: {selected.map((c) => `${c.label} (ID ${c.id})`).join(", ")}
        </p>
      )}
      {loading && <p>Loading choices…</p>}
      {error && <p role="alert">Unable to load choices.</p>}
      {page?.items.map((choice) => (
        <label key={choice.id}>
          <input
            type={kind === "principal" ? "radio" : "checkbox"}
            name={kind}
            checked={selected.some((c) => c.id === choice.id)}
            onChange={(e) =>
              onChange(
                kind === "principal"
                  ? [choice]
                  : e.target.checked
                  ? [...selected, choice]
                  : selected.filter((c) => c.id !== choice.id)
              )
            }
          />
          {choice.label} (ID {choice.id})
        </label>
      ))}
      {page && (
        <PageButtons
          offset={offset}
          count={page.items.length}
          total={page.totalCount}
          onChange={setOffset}
        />
      )}
    </fieldset>
  );
}

function MintForm({
  busy,
  onMint,
}: {
  busy: boolean;
  onMint: (variables: Record<string, unknown>) => void;
}) {
  const [principal, setPrincipal] = useState<Choice[]>([]);
  const [corpuses, setCorpuses] = useState<Choice[]>([]);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [allCorpuses, setAllCorpuses] = useState(false);
  const [days, setDays] = useState(String(AUTOMATION_CREDENTIAL_DEFAULT_DAYS));
  const { data, error } = useQuery<{ automationCredentialScopes: string[] }>(
    GET_AUTOMATION_SCOPES,
    { fetchPolicy: "no-cache" }
  );
  const valid =
    principal.length === 1 &&
    name.trim() &&
    scopes.length > 0 &&
    (allCorpuses || corpuses.length > 0) &&
    Number.isInteger(Number(days)) &&
    Number(days) > 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !busy)
          onMint({
            userId: principal[0].id,
            name,
            scopes,
            corpusIds: allCorpuses ? null : corpuses.map((c) => c.id),
            allCorpuses,
            expiresDays: Number(days),
          });
      }}
    >
      <ChoicePicker
        kind="principal"
        selected={principal}
        onChange={setPrincipal}
      />
      <FormField>
        <label htmlFor="credential-name">Name</label>
        <Input
          id="credential-name"
          value={name}
          maxLength={AUTOMATION_CREDENTIAL_NAME_MAX_LENGTH}
          required
          onChange={(e) => setName(e.target.value)}
        />
      </FormField>
      <fieldset>
        <legend>Operation scopes</legend>
        {error && <p role="alert">Unable to load scopes.</p>}
        {data?.automationCredentialScopes.map((scope) => (
          <label key={scope}>
            <input
              type="checkbox"
              checked={scopes.includes(scope)}
              onChange={(e) =>
                setScopes(
                  e.target.checked
                    ? [...scopes, scope]
                    : scopes.filter((s) => s !== scope)
                )
              }
            />
            {scope}
          </label>
        ))}
      </fieldset>
      <label>
        <input
          type="checkbox"
          checked={allCorpuses}
          onChange={(e) => setAllCorpuses(e.target.checked)}
        />
        Allow all corpuses (including future corpuses)
      </label>
      {!allCorpuses && (
        <ChoicePicker
          kind="corpus"
          selected={corpuses}
          onChange={setCorpuses}
        />
      )}
      <FormField>
        <label htmlFor="credential-days">Expires in days</label>
        <Input
          id="credential-days"
          type="number"
          min={1}
          step={1}
          required
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
      </FormField>
      <Button type="submit" disabled={!valid || busy}>
        Mint credential
      </Button>
    </form>
  );
}

function CredentialAdmin() {
  const client = useApolloClient();
  const [offset, setOffset] = useState(0);
  const [showMint, setShowMint] = useState(false);
  const [detail, setDetail] = useState<AutomationCredential | null>(null);
  const [action, setAction] = useState<"rotate" | "revoke" | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const {
    data,
    loading,
    error: queryError,
    refetch,
  } = useQuery<{
    automationCredentials: {
      items: AutomationCredential[];
      totalCount: number;
    };
  }>(GET_AUTOMATION_CREDENTIALS, {
    variables: { offset },
    fetchPolicy: "no-cache",
  });
  const page = data?.automationCredentials;

  async function readDetail(id: string) {
    const result = await client.query<{
      automationCredential: AutomationCredential;
    }>({
      query: GET_AUTOMATION_CREDENTIAL,
      variables: { id },
      fetchPolicy: "no-cache",
    });
    return result.data.automationCredential;
  }

  async function inspect(id: string) {
    setBusy(true);
    setError("");
    setAction(null);
    try {
      setDetail(await readDetail(id));
    } catch {
      setError("Unable to load credential details.");
    } finally {
      setBusy(false);
    }
  }

  async function run(
    mutation: DocumentNode,
    variables: Record<string, unknown>,
    field: string
  ) {
    setBusy(true);
    setError("");
    try {
      // Direct client calls avoid retaining one-time tokens in useMutation state.
      const result = await client.mutate<Record<string, { token?: string }>>({
        mutation,
        variables,
        fetchPolicy: "no-cache",
      });
      setToken(result.data?.[field]?.token ?? null);
      setCopied(false);
      setShowMint(false);
      setDetail(null);
      setAction(null);
      await refetch().catch(() => {
        setError("Credential saved, but the list could not be refreshed.");
      });
    } catch {
      setError(
        "Unable to complete the credential operation. Refresh and try again."
      );
      if (detail) {
        setAction(null);
        await readDetail(detail.id)
          .then(setDetail)
          .catch(() => setDetail(null));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Container>
      <Link to="/admin/settings">Back to admin settings</Link>
      <h1>Automation credentials</h1>
      <p>
        Access is limited by scopes, corpus restrictions and the principal’s
        existing permissions. Creating a credential grants no user permissions.
      </p>
      {((error && !detail && !token) || queryError) && (
        <p role="alert">{error || "Unable to load credentials."}</p>
      )}
      <Button onClick={() => setShowMint(!showMint)} disabled={busy || !!token}>
        {showMint ? "Cancel mint" : "New credential"}
      </Button>
      {showMint && (
        <CardSegment>
          <MintForm
            busy={busy}
            onMint={(variables) =>
              void run(
                MINT_AUTOMATION_CREDENTIAL,
                variables,
                "mintAutomationCredential"
              )
            }
          />
        </CardSegment>
      )}
      {loading && <p>Loading credentials…</p>}
      {page && (
        <>
          <ScrollableTableWrapper $minWidth={`${TABLET_BREAKPOINT}px`}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Principal</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((credential) => (
                  <tr key={credential.id}>
                    <td>{credential.name}</td>
                    <td>
                      {credential.username} (ID {credential.userId})
                    </td>
                    <td>{credential.status}</td>
                    <td>{credential.expiresAt ?? "No expiry"}</td>
                    <td>
                      <Button
                        variant="secondary"
                        disabled={busy || !!token}
                        onClick={() => {
                          void inspect(credential.id);
                        }}
                      >
                        Inspect {credential.name}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollableTableWrapper>
          {!page.items.length && <p>No credentials found.</p>}
          <PageButtons
            offset={offset}
            count={page.items.length}
            total={page.totalCount}
            onChange={setOffset}
          />
        </>
      )}
      <Modal
        open={!!detail}
        onClose={() => {
          if (!busy) {
            setDetail(null);
            setAction(null);
          }
        }}
      >
        <ModalHeader title={detail?.name ?? "Credential"} />
        <ModalBody>
          {error && <p role="alert">{error}</p>}
          {detail && (
            <>
              <dl>
                <dt>Credential ID</dt>
                <dd>
                  <code>{detail.id}</code>
                </dd>
                <dt>Principal</dt>
                <dd>
                  {detail.username} (ID {detail.userId})
                </dd>
                <dt>Status</dt>
                <dd>{detail.status}</dd>
                <dt>Scopes</dt>
                <dd>{detail.scopes.join(", ")}</dd>
                <dt>Corpus IDs</dt>
                <dd>
                  {detail.corpusIds === null
                    ? "All corpuses"
                    : detail.corpusIds.join(", ") || "None"}
                </dd>
                <dt>Created</dt>
                <dd>{detail.createdAt}</dd>
                <dt>Expires</dt>
                <dd>{detail.expiresAt ?? "No expiry"}</dd>
                <dt>Rotated</dt>
                <dd>{detail.rotatedAt ?? "Never"}</dd>
                <dt>Revoked</dt>
                <dd>{detail.revokedAt ?? "Never"}</dd>
              </dl>
              {action && (
                <p>
                  {action === "rotate"
                    ? "Rotation immediately invalidates the old token. Save the replacement before dismissing it."
                    : "Revocation permanently blocks new requests using this credential."}
                </p>
              )}
            </>
          )}
        </ModalBody>
        <ModalFooter>
          {action ? (
            <Button
              disabled={busy}
              onClick={() =>
                detail &&
                void run(
                  action === "rotate"
                    ? ROTATE_AUTOMATION_CREDENTIAL
                    : REVOKE_AUTOMATION_CREDENTIAL,
                  { id: detail.id },
                  action === "rotate"
                    ? "rotateAutomationCredential"
                    : "revokeAutomationCredential"
                )
              }
            >
              Confirm {action}
            </Button>
          ) : (
            <>
              <Button
                disabled={detail?.status !== "active"}
                onClick={() => setAction("rotate")}
              >
                Rotate
              </Button>
              <Button
                disabled={detail?.status === "revoked"}
                onClick={() => setAction("revoke")}
              >
                Revoke
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => {
              setDetail(null);
              setAction(null);
            }}
          >
            Close
          </Button>
        </ModalFooter>
      </Modal>
      <Modal
        open={token !== null}
        onClose={() => {
          setToken(null);
          setCopied(false);
        }}
      >
        <ModalHeader title="Save your token now" />
        <ModalBody>
          {error && <p role="alert">{error}</p>}
          <p>
            This token is shown once. Copy it to a secure location before
            dismissing.
          </p>
          <code>{token}</code>
        </ModalBody>
        <ModalFooter>
          <Button
            onClick={async () => {
              if (!token) return;
              try {
                await navigator.clipboard.writeText(token);
                setCopied(true);
              } catch {
                setError(
                  "Clipboard unavailable. Select and copy the token manually."
                );
              }
            }}
          >
            {copied ? "Copied" : "Copy token"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setToken(null);
              setCopied(false);
            }}
          >
            Dismiss token
          </Button>
        </ModalFooter>
      </Modal>
    </Container>
  );
}

export function AutomationCredentialManagement() {
  const user = useReactiveVar(backendUserObj);
  // Remount on identity changes so an issued token cannot survive logout/login.
  return user?.isSuperuser ? (
    <CredentialAdmin key={user.id} />
  ) : (
    <p role="alert">An active superuser login is required.</p>
  );
}
