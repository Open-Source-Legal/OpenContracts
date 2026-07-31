/**
 * Authority Packs tab — browse the server's configured pack catalog and open a
 * fresh, structured preflight before any installation.
 *
 * This is intentionally a catalog, not a file picker: authority packs can
 * include trusted server-side provider code, so the browser never supplies a
 * path, URL, archive, or manifest body.
 */
import React, { useState } from "react";
import { useQuery } from "@apollo/client";
import { Button } from "@os-legal/ui";
import { PackageOpen, RefreshCw, ShieldCheck } from "lucide-react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  AuthorityPack,
  AuthorityPackCorpus,
  GetAuthorityPacksOutputs,
  GET_AUTHORITY_PACKS,
} from "../../../graphql/queries";
import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";
import { Badge, KeyCell, Muted } from "./shared/consoleChrome";
import { humanizeCode } from "./shared/tones";
import { PackPreflightModal } from "./PackPreflightModal";

const Toolbar = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
`;

const Heading = styled.h2`
  margin: 0;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 1.05rem;
`;

const Intro = styled.p`
  margin: 0.35rem 0 0;
  max-width: 46rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.82rem;
  line-height: 1.5;
`;

const CatalogNote = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  margin-bottom: 1rem;
  padding: 0.7rem 0.8rem;
  color: ${OS_LEGAL_COLORS.infoText};
  background: ${OS_LEGAL_COLORS.infoSurface};
  border: 1px solid ${OS_LEGAL_COLORS.infoBorder};
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.45;

  svg {
    flex: 0 0 auto;
    margin-top: 0.1rem;
  }
`;

const CatalogGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 0.85rem;
`;

const PackCard = styled.article`
  display: flex;
  flex-direction: column;
  min-height: 240px;
  padding: 1rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
`;

const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
`;

const CardTitle = styled.h3`
  margin: 0;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 0.94rem;
`;

const CardDescription = styled.p`
  margin: 0.55rem 0 0;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8rem;
  line-height: 1.45;
`;

const BadgeRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.75rem;
`;

const StatusGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.85rem 0 0;
`;

const StatusItem = styled.div`
  min-width: 0;

  dt {
    color: ${OS_LEGAL_COLORS.textMuted};
    font-size: 0.68rem;
  }

  dd {
    margin: 0.1rem 0 0;
    color: ${OS_LEGAL_COLORS.textPrimary};
    font-size: 0.82rem;
    font-weight: 600;
  }
`;

const ValidationError = styled.p`
  margin: 0.7rem 0 0;
  color: ${OS_LEGAL_COLORS.dangerText};
  font-size: 0.76rem;
  line-height: 1.4;
`;

const CardFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: auto;
  padding-top: 1rem;
`;

const packStatus = (
  pack: AuthorityPack
): {
  label: string;
  tone: "success" | "info" | "warning" | "danger" | "neutral";
} => {
  if (!pack.valid) return { label: "Invalid", tone: "danger" };
  if (pack.fullyPublic) return { label: "Fully public", tone: "success" };
  if (pack.publicCount > 0) {
    return { label: "Partially public", tone: "warning" };
  }
  if (pack.installed) return { label: "Installed privately", tone: "info" };
  if (pack.installedCount > 0) {
    return { label: "Partially installed", tone: "warning" };
  }
  return { label: "Available", tone: "neutral" };
};

interface PacksTabProps {
  /**
   * Optional bridge to the existing corpus ZIP importer. The pack UI supplies
   * a validated installed corpus id; it does not duplicate upload machinery.
   */
  onImportCorpus?: (corpusId: string, corpus: AuthorityPackCorpus) => void;
}

export const PacksTab: React.FC<PacksTabProps> = ({ onImportCorpus }) => {
  const [selectedPackId, setSelectedPackId] = useState<string | null>(null);
  const { data, loading, error, refetch } = useQuery<GetAuthorityPacksOutputs>(
    GET_AUTHORITY_PACKS,
    {
      fetchPolicy: "network-only",
    }
  );
  const packs = data?.authorityPacks ?? [];

  const closePreflight = () => setSelectedPackId(null);
  const importIntoCorpus = (corpusId: string, corpus: AuthorityPackCorpus) => {
    // Avoid stacking two modal focus traps. The existing target-aware corpus
    // importer opens after this pack preflight is dismissed.
    closePreflight();
    onImportCorpus?.(corpusId, corpus);
  };

  return (
    <div data-testid="authority-packs-tab">
      <Toolbar>
        <div>
          <Heading>Authority packs</Heading>
          <Intro>
            Install reusable corpus definitions, taxonomies, mappings, and
            source metadata that have already been placed on this server.
          </Intro>
        </div>
        <Button
          variant="secondary"
          size="sm"
          leftIcon={<RefreshCw size={14} />}
          loading={loading && packs.length > 0}
          disabled={loading && packs.length > 0}
          onClick={() => refetch()}
          data-testid="packs-refresh"
        >
          Refresh
        </Button>
      </Toolbar>

      <CatalogNote data-testid="packs-server-catalog-note">
        <ShieldCheck size={16} />
        <span>
          This catalog is discovered from server-configured authority-pack
          directories. For safety, the browser cannot upload pack code or submit
          a filesystem path or remote URL. Installing a pack does not crawl its
          source sites.
        </span>
      </CatalogNote>

      {loading && packs.length === 0 ? (
        <LoadingState message="Loading authority packs…" />
      ) : error ? (
        <ErrorMessage title="Could not load authority packs">
          {error.message}
        </ErrorMessage>
      ) : packs.length === 0 ? (
        <InfoMessage title="No authority packs available">
          Place a supported pack in a server-configured authority-pack
          directory, then refresh this catalog.
        </InfoMessage>
      ) : (
        <CatalogGrid data-testid="packs-catalog">
          {packs.map((pack) => {
            const status = packStatus(pack);
            return (
              <PackCard key={pack.id} data-testid="pack-card">
                <CardHeader>
                  <div>
                    <CardTitle>{pack.displayName || pack.name}</CardTitle>
                    <KeyCell>{pack.name}</KeyCell>
                  </div>
                  <Badge $tone={status.tone}>{status.label}</Badge>
                </CardHeader>

                <CardDescription>
                  {pack.description || "No pack description provided."}
                </CardDescription>

                <BadgeRow>
                  <Badge $tone="neutral">{pack.jurisdiction}</Badge>
                  <Badge $tone="neutral">Manifest v{pack.schemaVersion}</Badge>
                  <Badge
                    $tone={
                      pack.approvalStatus.toLowerCase() === "approved"
                        ? "success"
                        : "warning"
                    }
                  >
                    {humanizeCode(pack.approvalStatus)}
                  </Badge>
                </BadgeRow>

                <StatusGrid>
                  <StatusItem>
                    <dt>Corpora</dt>
                    <dd>{pack.totalCorpora}</dd>
                  </StatusItem>
                  <StatusItem>
                    <dt>Installed</dt>
                    <dd>
                      {pack.installedCount}/{pack.totalCorpora}
                    </dd>
                  </StatusItem>
                  <StatusItem>
                    <dt>Public</dt>
                    <dd>
                      {pack.publicCount}/{pack.totalCorpora}
                    </dd>
                  </StatusItem>
                </StatusGrid>

                {!pack.valid && (
                  <ValidationError>
                    {pack.validationError || "Manifest validation failed."}
                  </ValidationError>
                )}

                <CardFooter>
                  <Muted>
                    {pack.sourceHosts.length
                      ? `${pack.sourceHosts.length} declared source ${
                          pack.sourceHosts.length === 1 ? "host" : "hosts"
                        }`
                      : "No external source hosts"}
                  </Muted>
                  <Button
                    variant="primary"
                    size="sm"
                    leftIcon={<PackageOpen size={15} />}
                    disabled={!pack.valid}
                    title={
                      pack.valid
                        ? undefined
                        : "Repair this server-deployed pack before installing it."
                    }
                    onClick={() => setSelectedPackId(pack.id)}
                    data-testid={`pack-review-${pack.id}`}
                  >
                    {pack.canInstall ? "Review & install" : "Review pack"}
                  </Button>
                </CardFooter>
              </PackCard>
            );
          })}
        </CatalogGrid>
      )}

      <PackPreflightModal
        packId={selectedPackId}
        open={selectedPackId !== null}
        onClose={closePreflight}
        onInstalled={() => refetch()}
        onImportCorpus={onImportCorpus ? importIntoCorpus : undefined}
      />
    </div>
  );
};
