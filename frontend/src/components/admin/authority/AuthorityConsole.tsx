/**
 * Authority Console — the single front door for managing legal authorities.
 *
 * Replaces the three disconnected, flat-sibling admin panels (Authority Sources
 * / Authority Mappings / Enrichment Runner) with one shell: a left tab rail +
 * a single "Back to Admin Settings" link, gated once at mount by the authority-
 * admin check. The active tab + (for the registry) the selected authority prefix
 * live in the URL, so every view is deep-linkable.
 *
 * Phase 1 ships the Registry tab (AuthorityNamespace management — the headline
 * gap). The remaining concerns (relationships, discovery queue, scrapers/
 * credentials, runs) are absorbed into real tabs in later phases; until then
 * their rail entries open the existing standalone panels.
 */
import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@os-legal/ui";
import {
  ArrowLeft,
  BookMarked,
  Database,
  ExternalLink,
  GitBranch,
  Library,
  LucideIcon,
  Scale,
  Zap,
} from "lucide-react";

import { WarningMessage } from "../../widgets/feedback";
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
import { PlaceholderTab } from "./PlaceholderTab";

type TabKey = "registry" | "mappings" | "queue" | "scrapers" | "runs";

interface TabDef {
  key: TabKey;
  label: string;
  icon: LucideIcon;
  /** Existing standalone route this concern lives at until it is absorbed. */
  legacyRoute?: string;
  legacyLabel?: string;
  description?: string;
}

const TABS: TabDef[] = [
  { key: "registry", label: "Authorities", icon: Library },
  { key: "mappings", label: "Aliases & Relationships", icon: GitBranch },
  { key: "queue", label: "Discovery Queue", icon: Scale },
  {
    key: "scrapers",
    label: "Scrapers & Credentials",
    icon: Database,
    description:
      "View the registered authority source providers (US Code, eCFR, Federal " +
      "Register, …) and manage their credentials. This tab lands in a later phase.",
  },
  {
    key: "runs",
    label: "Runs",
    icon: Zap,
    legacyRoute: "/admin/enrichment",
    legacyLabel: "Enrichment Runner",
    description:
      "Dispatch reference enrichment and authority discovery on a corpus and " +
      "review job status. This tab opens the existing Enrichment Runner for now.",
  },
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

  const activeDef = TABS.find((t) => t.key === tab) ?? TABS[0];

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
            One place to view, manage and edit legal authorities — the bodies of
            law whose aliases drive citation extraction — together with their
            aliases, relationships, discovery status, and scrapers.
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
          {tab === "registry" ? (
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
          ) : (
            <PlaceholderTab
              title={activeDef.label}
              description={activeDef.description ?? ""}
              action={
                activeDef.legacyRoute ? (
                  <Button
                    variant="primary"
                    onClick={() => navigate(activeDef.legacyRoute as string)}
                    data-testid={`authority-open-${activeDef.key}`}
                  >
                    <ExternalLink size={14} style={{ marginRight: 6 }} />
                    Open {activeDef.legacyLabel}
                  </Button>
                ) : null
              }
            />
          )}
        </TabContent>
      </ConsoleLayout>
    </Container>
  );
};
