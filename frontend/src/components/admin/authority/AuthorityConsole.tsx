/**
 * Authority Console — the single front door for managing legal authorities.
 *
 * Replaces the three disconnected, flat-sibling admin panels (Authority Sources
 * / Authority Mappings / Enrichment Runner) with one shell: a left tab rail +
 * a single "Back to Admin Settings" link, gated once at mount by the authority-
 * admin check. The active tab + (for the registry) the selected authority prefix
 * live in the URL, so every view is deep-linkable. Authority packs,
 * authorities, aliases & relationships, the discovery queue, scrapers, and
 * runs are absorbed here as real tabs (the standalone panels they replaced are
 * deleted).
 */
import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  BookMarked,
  Database,
  GitBranch,
  Library,
  LucideIcon,
  PackageOpen,
  Scale,
  Zap,
} from "lucide-react";

import { WarningMessage } from "../../widgets/feedback";
import {
  ImportCorpusModal,
  ImportCorpusTarget,
} from "../../widgets/modals/ImportCorpusModal";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  BackLink,
  Container,
  ConsoleLayout,
  PageHeader,
  PageSubtitle,
  PageTitle,
  TabButton,
  TabContent,
  TabRail,
} from "./shared/consoleChrome";
import { useIsAuthorityAdmin } from "./hooks/useIsAuthorityAdmin";
import { RegistryTab } from "./RegistryTab";
import { MappingsTab } from "./MappingsTab";
import { DiscoveryQueueTab } from "./DiscoveryQueueTab";
import { ScrapersTab } from "./ScrapersTab";
import { RunsTab } from "./RunsTab";
import { PacksTab } from "./PacksTab";

type TabKey = "packs" | "registry" | "mappings" | "queue" | "scrapers" | "runs";

interface TabDef {
  key: TabKey;
  label: string;
  icon: LucideIcon;
}

const TABS: TabDef[] = [
  { key: "packs", label: "Authority Packs", icon: PackageOpen },
  { key: "registry", label: "Authorities", icon: Library },
  { key: "mappings", label: "Aliases & Relationships", icon: GitBranch },
  { key: "queue", label: "Discovery Queue", icon: Scale },
  { key: "scrapers", label: "Scrapers & Credentials", icon: Database },
  { key: "runs", label: "Runs", icon: Zap },
];

const ROOT = "/admin/authority";

interface ParsedPath {
  tab: TabKey;
  prefix: string | null;
}

function parsePath(pathname: string): ParsedPath {
  // /admin/authority[/<tab>[/<prefix...>]]
  const rest = pathname.replace(/^\/admin\/authority\/?/, "");
  const segments = rest.split("/").filter(Boolean);
  const tab = (segments[0] as TabKey) || "registry";
  const known = TABS.some((t) => t.key === tab) ? tab : "registry";
  // The registry detail carries the authority prefix (may contain no slashes).
  const prefix =
    known === "registry" && segments[1]
      ? decodeURIComponent(segments.slice(1).join("/"))
      : null;
  return { tab: known, prefix };
}

export const AuthorityConsole: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [importTarget, setImportTarget] = useState<ImportCorpusTarget | null>(
    null
  );
  const { ready, isAdmin } = useIsAuthorityAdmin();
  const { tab, prefix } = parsePath(location.pathname);

  if (!ready) {
    return null;
  }
  if (!isAdmin) {
    return (
      <Container>
        <WarningMessage title="Access Denied">
          Only administrators can manage legal authorities.
        </WarningMessage>
      </Container>
    );
  }

  return (
    <Container data-testid="authority-console">
      <BackLink
        onClick={() => navigate("/admin/settings")}
        data-testid="authority-console-back"
      >
        <ArrowLeft size={14} />
        Back to Admin Settings
      </BackLink>

      <PageHeader>
        <div>
          <PageTitle>
            <BookMarked size={26} color={OS_LEGAL_COLORS.folderIcon} />
            Authority Console
          </PageTitle>
          <PageSubtitle>
            One place to install authority packs and manage legal authorities —
            the bodies of law whose aliases drive citation extraction — together
            with their aliases, relationships, sideloaded corpora, and run
            history.
          </PageSubtitle>
        </div>
      </PageHeader>

      <ConsoleLayout>
        <TabRail aria-label="Authority Console sections">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <TabButton
                key={t.key}
                type="button"
                $active={t.key === tab}
                onClick={() => navigate(`${ROOT}/${t.key}`)}
                data-testid={`authority-tab-${t.key}`}
              >
                <Icon size={16} />
                {t.label}
              </TabButton>
            );
          })}
        </TabRail>

        <TabContent>
          {tab === "packs" ? (
            <PacksTab
              onImportCorpus={(corpusId, corpus) =>
                setImportTarget({ id: corpusId, title: corpus.title })
              }
            />
          ) : tab === "registry" ? (
            <RegistryTab
              selectedPrefix={prefix}
              onOpenAuthority={(p) =>
                navigate(`${ROOT}/registry/${encodeURIComponent(p)}`)
              }
              onCloseAuthority={() => navigate(`${ROOT}/registry`)}
            />
          ) : tab === "mappings" ? (
            <MappingsTab />
          ) : tab === "queue" ? (
            <DiscoveryQueueTab />
          ) : tab === "scrapers" ? (
            <ScrapersTab />
          ) : (
            <RunsTab />
          )}
        </TabContent>
      </ConsoleLayout>

      <ImportCorpusModal
        visible={importTarget !== null}
        targetCorpus={importTarget}
        onClose={() => setImportTarget(null)}
      />
    </Container>
  );
};
