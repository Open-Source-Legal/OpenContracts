/**
 * Structured preflight + install dialog for one server-discovered authority
 * pack. The client sends only the opaque pack id and the fingerprint returned
 * by this fresh preflight; paths, URLs, and uploaded pack code are deliberately
 * outside this flow.
 */
import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Table,
} from "@os-legal/ui";
import { FileArchive, Globe2, LockKeyhole, X } from "lucide-react";
import styled from "styled-components";
import { toast } from "react-toastify";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  AuthorityPackCorpus,
  GetAuthorityPackPreflightInputs,
  GetAuthorityPackPreflightOutputs,
  GET_AUTHORITY_PACK_PREFLIGHT,
} from "../../../graphql/queries";
import {
  InstallAuthorityPackInputs,
  InstallAuthorityPackOutputs,
  INSTALL_AUTHORITY_PACK,
} from "../../../graphql/mutations";
import { ScrollableTableWrapper } from "../../layout/SharedSegments";
import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
  WarningMessage,
} from "../../widgets/feedback";
import { Badge, KeyCell, Muted } from "./shared/consoleChrome";
import { humanizeCode } from "./shared/tones";

const SummaryHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
`;

const PackName = styled.h3`
  margin: 0;
  font-size: 1rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const Description = styled.p`
  margin: 0.35rem 0 0;
  max-width: 42rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.84rem;
  line-height: 1.5;
`;

const BadgeRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.65rem;
`;

const MetricGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.6rem;
  margin: 1rem 0;

  @media (max-width: 620px) {
    grid-template-columns: 1fr;
  }
`;

const Metric = styled.div`
  padding: 0.65rem 0.75rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
`;

const MetricValue = styled.div`
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 1.1rem;
  font-weight: 700;
`;

const MetricLabel = styled.div`
  margin-top: 0.1rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.74rem;
`;

const Section = styled.section`
  margin-top: 1rem;
`;

const SectionTitle = styled.h4`
  margin: 0 0 0.45rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 0.82rem;
`;

const HostList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
`;

const Fingerprint = styled.code`
  display: block;
  padding: 0.45rem 0.55rem;
  overflow-wrap: anywhere;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  font-size: 0.72rem;
`;

const InstallOptions = styled.fieldset`
  margin: 1rem 0 0;
  padding: 0.8rem 0.9rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
`;

const OptionLabel = styled.label<{ $disabled: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  color: ${(p) =>
    p.$disabled ? OS_LEGAL_COLORS.textMuted : OS_LEGAL_COLORS.textPrimary};
  font-size: 0.84rem;
  font-weight: 600;
  cursor: ${(p) => (p.$disabled ? "not-allowed" : "pointer")};

  input {
    margin-top: 0.15rem;
  }
`;

const OptionHelp = styled.p`
  margin: 0.3rem 0 0 1.5rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.76rem;
  line-height: 1.45;
`;

const InlineError = styled.div`
  margin-top: 1rem;
`;

const CORPORA_TABLE_MIN_WIDTH_PX = 760;

const approvalTone = (
  approvalStatus: string
): "success" | "warning" | "neutral" => {
  const normalized = approvalStatus.trim().toLowerCase();
  if (normalized === "approved") return "success";
  if (normalized.includes("pending") || normalized.includes("review")) {
    return "warning";
  }
  return "neutral";
};

interface PackPreflightModalProps {
  packId: string | null;
  open: boolean;
  onClose: () => void;
  onInstalled: () => Promise<unknown> | unknown;
  /**
   * Clean seam into the existing corpus ZIP importer. The importer is owned by
   * the corpus UI; this pack flow only supplies the installed target corpus.
   */
  onImportCorpus?: (corpusId: string, corpus: AuthorityPackCorpus) => void;
}

export const PackPreflightModal: React.FC<PackPreflightModalProps> = ({
  packId,
  open,
  onClose,
  onInstalled,
  onImportCorpus,
}) => {
  const [publish, setPublish] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);

  const { data, loading, error } = useQuery<
    GetAuthorityPackPreflightOutputs,
    GetAuthorityPackPreflightInputs
  >(GET_AUTHORITY_PACK_PREFLIGHT, {
    variables: { packId: packId ?? "" },
    skip: !open || !packId,
    fetchPolicy: "network-only",
  });
  const pack = data?.authorityPackPreflight ?? null;

  const [installPack, { loading: installing }] = useMutation<
    InstallAuthorityPackOutputs,
    InstallAuthorityPackInputs
  >(INSTALL_AUTHORITY_PACK);

  useEffect(() => {
    if (open) {
      setPublish(false);
      setInstallError(null);
    }
  }, [open, packId]);

  useEffect(() => {
    if (pack && !pack.canPublish) setPublish(false);
  }, [pack]);

  const handleClose = () => {
    if (!installing) onClose();
  };

  const handleInstall = async () => {
    if (
      !pack ||
      !pack.valid ||
      !pack.canInstall ||
      (publish && !pack.canPublish) ||
      installing
    ) {
      return;
    }

    setInstallError(null);
    try {
      const { data: installData } = await installPack({
        variables: {
          packId: pack.id,
          expectedFingerprint: pack.fingerprint,
          publish,
        },
      });
      const result = installData?.installAuthorityPack;
      if (!result?.ok) {
        const message = result?.message ?? "Could not install authority pack.";
        setInstallError(message);
        toast.error(message);
        return;
      }

      // A post-commit step (the reactive relink, the response refresh) can fail
      // after the pack is already written. The server keeps ok=true — the
      // install happened — and appends the detail to `message`, so a green
      // success toast would read as "all clear" for a run that half-worked.
      // Branch on the structured `warnings` the payload also carries.
      const warnings = result.result?.warnings ?? [];
      const successMessage =
        result.message ??
        (publish
          ? "Authority pack installed and published."
          : "Authority pack installed privately.");
      if (warnings.length > 0) {
        toast.warning(successMessage);
      } else {
        toast.success(successMessage);
      }
      await onInstalled();
      onClose();
    } catch (installFailure) {
      const message =
        installFailure instanceof Error
          ? installFailure.message
          : "Could not install authority pack.";
      setInstallError(message);
      toast.error(message);
    }
  };

  const title = pack
    ? `Preflight: ${pack.displayName || pack.name}`
    : "Authority pack preflight";

  return (
    <Modal open={open} onClose={handleClose} size="lg">
      <ModalHeader
        title={<span data-testid="pack-preflight-title">{title}</span>}
        subtitle="Review the server-validated manifest before changing any corpora."
        onClose={handleClose}
        showCloseButton={!installing}
      />
      <ModalBody>
        <div data-testid="authority-pack-preflight">
          {loading ? (
            <LoadingState message="Validating authority pack…" />
          ) : error ? (
            <ErrorMessage title="Could not preflight pack">
              {error.message}
            </ErrorMessage>
          ) : !pack ? (
            <InfoMessage title="Pack unavailable">
              The server did not return a preflight for this pack.
            </InfoMessage>
          ) : (
            <>
              <SummaryHeader>
                <div>
                  <PackName>{pack.displayName || pack.name}</PackName>
                  <Description>{pack.description}</Description>
                  <BadgeRow>
                    <Badge $tone="neutral">{pack.jurisdiction}</Badge>
                    <Badge $tone="neutral">
                      Manifest v{pack.schemaVersion}
                    </Badge>
                    <Badge $tone={approvalTone(pack.approvalStatus)}>
                      {humanizeCode(pack.approvalStatus)}
                    </Badge>
                    <Badge $tone={pack.valid ? "success" : "danger"}>
                      {pack.valid ? "Validated" : "Invalid"}
                    </Badge>
                  </BadgeRow>
                </div>
                {pack.fullyPublic ? (
                  <Badge $tone="success">Fully public</Badge>
                ) : pack.publicCount > 0 ? (
                  <Badge $tone="warning">Partially public</Badge>
                ) : pack.installed ? (
                  <Badge $tone="info">Installed privately</Badge>
                ) : pack.installedCount > 0 ? (
                  <Badge $tone="warning">Partially installed</Badge>
                ) : (
                  <Badge $tone="neutral">Not installed</Badge>
                )}
              </SummaryHeader>

              {!pack.valid && (
                <ErrorMessage title="Pack failed validation">
                  {pack.validationError ||
                    "The manifest did not pass server validation."}
                </ErrorMessage>
              )}

              {pack.valid && !pack.canPublish && (
                <WarningMessage
                  title="Publication unavailable"
                  style={{ marginTop: "0.75rem" }}
                >
                  This pack can only be installed privately. Its approval or
                  legal-review requirements do not permit public visibility.
                </WarningMessage>
              )}

              <MetricGrid aria-label="Pack corpus status">
                <Metric>
                  <MetricValue>{pack.totalCorpora}</MetricValue>
                  <MetricLabel>Total corpora</MetricLabel>
                </Metric>
                <Metric>
                  <MetricValue>{pack.installedCount}</MetricValue>
                  <MetricLabel>Installed for this administrator</MetricLabel>
                </Metric>
                <Metric>
                  <MetricValue>{pack.publicCount}</MetricValue>
                  <MetricLabel>Public corpora</MetricLabel>
                </Metric>
              </MetricGrid>

              <Section>
                <SectionTitle>Manifest fingerprint</SectionTitle>
                <Fingerprint data-testid="pack-fingerprint">
                  {pack.fingerprint}
                </Fingerprint>
              </Section>

              <Section>
                <SectionTitle>Declared source hosts</SectionTitle>
                {pack.sourceHosts.length ? (
                  <HostList>
                    {pack.sourceHosts.map((host) => (
                      <KeyCell key={host}>{host}</KeyCell>
                    ))}
                  </HostList>
                ) : (
                  <Muted>No external source hosts declared.</Muted>
                )}
              </Section>

              <Section>
                <SectionTitle>Corpora in this pack</SectionTitle>
                <ScrollableTableWrapper
                  $minWidth={`${CORPORA_TABLE_MIN_WIDTH_PX}px`}
                  data-testid="pack-corpora-table"
                >
                  <Table variant="minimal">
                    <Table.Head>
                      <Table.Row>
                        <Table.HeadCell>Corpus</Table.HeadCell>
                        <Table.HeadCell>Approval</Table.HeadCell>
                        <Table.HeadCell>Installation</Table.HeadCell>
                        <Table.HeadCell>Visibility</Table.HeadCell>
                        <Table.HeadCell>Sideload content</Table.HeadCell>
                      </Table.Row>
                    </Table.Head>
                    <Table.Body>
                      {pack.corpora.map((corpus) => (
                        <Table.Row
                          key={corpus.slug}
                          data-testid="pack-corpus-row"
                        >
                          <Table.Cell>
                            <div style={{ fontWeight: 600 }}>
                              {corpus.title}
                            </div>
                            <KeyCell>{corpus.slug}</KeyCell>
                          </Table.Cell>
                          <Table.Cell>
                            <Badge $tone={approvalTone(corpus.approvalStatus)}>
                              {humanizeCode(corpus.approvalStatus)}
                            </Badge>
                          </Table.Cell>
                          <Table.Cell>
                            <Badge
                              $tone={corpus.installed ? "success" : "neutral"}
                            >
                              {corpus.installed ? "Installed" : "Not installed"}
                            </Badge>
                          </Table.Cell>
                          <Table.Cell>
                            <Badge
                              $tone={corpus.isPublic ? "success" : "neutral"}
                            >
                              {corpus.isPublic ? "Public" : "Private"}
                            </Badge>
                          </Table.Cell>
                          <Table.Cell>
                            {corpus.installed && corpus.corpusId ? (
                              <Button
                                variant="secondary"
                                size="sm"
                                leftIcon={<FileArchive size={14} />}
                                disabled={!onImportCorpus || installing}
                                title={
                                  onImportCorpus
                                    ? `Import an OpenContracts corpus ZIP into ${corpus.title}`
                                    : "Corpus ZIP import is not connected in this view."
                                }
                                data-testid={`pack-import-corpus-${corpus.slug}`}
                                onClick={() =>
                                  onImportCorpus?.(corpus.corpusId!, corpus)
                                }
                              >
                                Import corpus ZIP
                              </Button>
                            ) : corpus.installed ? (
                              <Muted>Corpus ID unavailable</Muted>
                            ) : (
                              <Muted>Install pack first</Muted>
                            )}
                          </Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>
                </ScrollableTableWrapper>
                <Description>
                  Corpus ZIP import reuses the existing sideload flow and
                  targets an installed corpus. Bundled seed specs install with
                  the pack; full corpus exports are uploaded separately.
                </Description>
              </Section>

              <InstallOptions>
                <OptionLabel
                  $disabled={!pack.canPublish || installing}
                  title={
                    pack.canPublish
                      ? undefined
                      : "This pack is not approved for publication."
                  }
                >
                  <input
                    type="checkbox"
                    checked={publish}
                    disabled={!pack.canPublish || installing}
                    data-testid="pack-publish-option"
                    onChange={(event) => setPublish(event.target.checked)}
                  />
                  <span>Make installed corpora public</span>
                </OptionLabel>
                <OptionHelp>
                  {pack.canPublish
                    ? "Optional. Leave this unchecked to install privately. Public corpora and their documents can be read anonymously."
                    : "Disabled until the server reports that every publication requirement is satisfied."}
                </OptionHelp>
              </InstallOptions>

              {publish && (
                <WarningMessage
                  title="Public access is explicit"
                  style={{ marginTop: "0.75rem" }}
                >
                  Installing with this option makes the pack corpora and their
                  imported documents anonymously readable.
                </WarningMessage>
              )}

              {installError && (
                <InlineError>
                  <ErrorMessage title="Installation failed">
                    {installError}
                  </ErrorMessage>
                </InlineError>
              )}
            </>
          )}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onClick={handleClose}
          disabled={installing}
          leftIcon={<X size={16} />}
        >
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handleInstall}
          loading={installing}
          disabled={
            !pack ||
            !pack.valid ||
            !pack.canInstall ||
            (publish && !pack.canPublish) ||
            installing
          }
          leftIcon={publish ? <Globe2 size={16} /> : <LockKeyhole size={16} />}
          data-testid="pack-install-submit"
        >
          {!pack?.canInstall
            ? "Nothing to install"
            : publish
            ? "Install and publish"
            : "Install privately"}
        </Button>
      </ModalFooter>
    </Modal>
  );
};
