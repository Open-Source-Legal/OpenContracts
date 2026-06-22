/**
 * Scrapers tab — read-only view of the registered authority source providers.
 *
 * The provider classes (US Code / eCFR / Federal Register / agentic web locator)
 * are auto-discovered code with no DB row, so until now they were invisible to
 * operators. This surfaces them: supported prefixes, license, priority, enabled
 * + requires-approval flags, and whether the secrets vault holds credentials.
 * Read-only by design — enabling/disabling a provider stays in code, and
 * credentials are edited via System Settings' component-secrets surface (the one
 * vault), not re-implemented here.
 */
import React from "react";
import { useQuery } from "@apollo/client";
import { Table } from "@os-legal/ui";
import styled from "styled-components";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";
import { ScrollableTableWrapper } from "../../layout/SharedSegments";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  GetAuthoritySourceProvidersOutputs,
  GET_AUTHORITY_SOURCE_PROVIDERS,
} from "../../../graphql/queries";
import { Badge, KeyCell, Muted } from "./shared/consoleChrome";

const SCRAPERS_TABLE_MIN_WIDTH_PX = 920;

const Note = styled.p`
  margin: 0 0 1rem;
  max-width: 46rem;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const PrefixList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  max-width: 22rem;
`;

export const ScrapersTab: React.FC = () => {
  const { data, loading, error } = useQuery<GetAuthoritySourceProvidersOutputs>(
    GET_AUTHORITY_SOURCE_PROVIDERS,
    { fetchPolicy: "network-only" }
  );
  const providers = data?.authoritySourceProviders ?? [];

  if (loading && providers.length === 0) {
    return <LoadingState message="Loading source providers…" />;
  }
  if (error) {
    return (
      <ErrorMessage title="Error loading source providers">
        {error.message}
      </ErrorMessage>
    );
  }

  return (
    <div data-testid="authority-scrapers-tab">
      <Note>
        Authority source providers ingest cited law from public-domain sources.
        They are auto-discovered code (no runtime registration). Credentials,
        when a provider needs them, are stored in the encrypted
        component-secrets vault and edited from System Settings — they are never
        managed here.
      </Note>

      {providers.length === 0 ? (
        <InfoMessage title="No source providers">
          No authority source providers are registered.
        </InfoMessage>
      ) : (
        <ScrollableTableWrapper
          $minWidth={`${SCRAPERS_TABLE_MIN_WIDTH_PX}px`}
          data-testid="scrapers-table-scroll"
        >
          <Table variant="minimal">
            <Table.Head>
              <Table.Row>
                <Table.HeadCell>Provider</Table.HeadCell>
                <Table.HeadCell>Prefixes</Table.HeadCell>
                <Table.HeadCell>License</Table.HeadCell>
                <Table.HeadCell>Priority</Table.HeadCell>
                <Table.HeadCell>Status</Table.HeadCell>
                <Table.HeadCell>Credentials</Table.HeadCell>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {providers.map((p) => (
                <Table.Row key={p.name} data-testid="scrapers-row">
                  <Table.Cell>
                    <div style={{ fontWeight: 600 }}>{p.title || p.name}</div>
                    <Muted>{p.name}</Muted>
                  </Table.Cell>
                  <Table.Cell>
                    {p.supportedPrefixes.length ? (
                      <PrefixList>
                        {p.supportedPrefixes.map((pref) => (
                          <KeyCell key={pref}>{pref}</KeyCell>
                        ))}
                      </PrefixList>
                    ) : (
                      <Muted>any (regex)</Muted>
                    )}
                  </Table.Cell>
                  <Table.Cell>
                    <Badge $tone="neutral">{p.license || "—"}</Badge>
                  </Table.Cell>
                  <Table.Cell>{p.priority ?? <Muted>—</Muted>}</Table.Cell>
                  <Table.Cell>
                    <Badge $tone={p.enabled ? "success" : "neutral"}>
                      {p.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                    {p.requiresApproval && (
                      <>
                        {" "}
                        <Badge $tone="warning">Needs approval</Badge>
                      </>
                    )}
                  </Table.Cell>
                  <Table.Cell>
                    {p.hasCredentials ? (
                      <Badge $tone="info">Stored</Badge>
                    ) : (
                      <Muted>none needed</Muted>
                    )}
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </ScrollableTableWrapper>
      )}
    </div>
  );
};
