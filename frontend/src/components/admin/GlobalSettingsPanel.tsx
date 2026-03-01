import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import {
  Trophy,
  Bot,
  Settings,
  Users,
  Upload,
  Workflow,
  LucideIcon,
} from "lucide-react";
import { Tabs, TabList, Tab, TabPanels, TabPanel } from "@os-legal/ui";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  OS_LEGAL_SPACING,
} from "../../assets/configurations/osLegalStyles";
import { SystemSettings } from "./SystemSettings";

// ============================================================================
// Styled Components
// ============================================================================

const Container = styled.div`
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;

  @media (max-width: 768px) {
    padding: 1rem;
  }

  @media (max-width: 480px) {
    padding: 0.75rem;
  }
`;

const PageHeader = styled.div`
  margin-bottom: 1.5rem;

  @media (max-width: 768px) {
    margin-bottom: 1rem;
    text-align: center;
  }
`;

const PageTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.75rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;

  @media (max-width: 768px) {
    font-size: 1.5rem;
    justify-content: center;
  }

  @media (max-width: 480px) {
    font-size: 1.3rem;
  }
`;

const PageDescription = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 1rem;
  margin: 0;
  line-height: 1.5;

  @media (max-width: 768px) {
    font-size: 0.9rem;
  }
`;

const TabContent = styled.div`
  margin-top: 1.5rem;
`;

const SettingsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;

  @media (max-width: 768px) {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
  }

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }
`;

const SettingsCard = styled.div<{ $disabled?: boolean }>`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  box-shadow: ${OS_LEGAL_SPACING.shadowCard};
  padding: 1.5rem;
  cursor: ${({ $disabled }) => ($disabled ? "default" : "pointer")};
  opacity: ${({ $disabled }) => ($disabled ? 0.6 : 1)};
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;

  ${({ $disabled }) =>
    !$disabled &&
    `
    &:hover {
      transform: translateY(-2px);
      box-shadow: ${OS_LEGAL_SPACING.shadowCardHover};
      border-color: ${OS_LEGAL_COLORS.borderHover};
    }

    @media (hover: none) {
      &:hover {
        transform: none;
        box-shadow: ${OS_LEGAL_SPACING.shadowCard};
        border-color: ${OS_LEGAL_COLORS.border};
      }

      &:active {
        transform: scale(0.98);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
      }
    }
  `}

  @media (max-width: 768px) {
    padding: 1.25rem;
  }

  @media (max-width: 480px) {
    padding: 1rem;
  }
`;

const CardIconWrapper = styled.div<{ $gradient: string }>`
  width: 48px;
  height: 48px;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  background: ${({ $gradient }) => $gradient};
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;

  @media (max-width: 768px) {
    width: 44px;
    height: 44px;
    margin-bottom: 0.75rem;
  }
`;

const CardTitle = styled.h3`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 1.125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;

  @media (max-width: 768px) {
    font-size: 1rem;
  }
`;

const CardDescription = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0;
  line-height: 1.5;

  @media (max-width: 768px) {
    font-size: 0.8rem;
  }
`;

const TabIcon = styled.span`
  display: inline-flex;
  margin-right: 6px;
  vertical-align: middle;
`;

const ComingSoonBadge = styled.span`
  display: inline-block;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  font-weight: 500;
  color: #8b5cf6;
  background: #f3e8ff;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  margin-left: 0.5rem;

  @media (max-width: 480px) {
    display: block;
    margin-left: 0;
    margin-top: 0.5rem;
    width: fit-content;
  }
`;

// ============================================================================
// Types & Data
// ============================================================================

interface SettingItem {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  gradient: string;
  route?: string;
  comingSoon?: boolean;
}

const overviewItems: SettingItem[] = [
  {
    id: "badges",
    title: "Badge Management",
    description:
      "Create and manage badges that can be awarded to users for achievements and contributions.",
    icon: Trophy,
    gradient: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
    route: "/admin/badges",
  },
  {
    id: "global-agents",
    title: "Global Agents",
    description:
      "Configure global AI agents available across all corpuses for document and corpus analysis.",
    icon: Bot,
    gradient: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
    route: "/admin/agents",
  },
  {
    id: "worker-accounts",
    title: "Worker Accounts",
    description:
      "Manage service accounts used by automated pipelines to upload and process documents.",
    icon: Upload,
    gradient: "linear-gradient(135deg, #0f766e 0%, #0d6860 100%)",
    route: "/admin/worker-accounts",
  },
  {
    id: "user-management",
    title: "User Management",
    description:
      "View and manage user accounts, permissions, and access controls.",
    icon: Users,
    gradient: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
    comingSoon: true,
  },
];

const ADMIN_TABS = [
  { value: "overview", label: "Overview" },
  { value: "pipeline", label: "Pipeline Configuration" },
] as const;

type AdminTab = (typeof ADMIN_TABS)[number]["value"];

// ============================================================================
// Component
// ============================================================================

export const GlobalSettingsPanel: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");

  const handleCardClick = useCallback(
    (item: SettingItem) => {
      if (item.route && !item.comingSoon) {
        navigate(item.route);
      }
    },
    [navigate]
  );

  return (
    <Container>
      <PageHeader>
        <PageTitle>
          <Settings size={28} color={OS_LEGAL_COLORS.accent} />
          Admin Settings
        </PageTitle>
        <PageDescription>
          Manage global settings, configurations, and administrative features
          for OpenContracts.
        </PageDescription>
      </PageHeader>

      <Tabs
        value={activeTab}
        onChange={(val: string) => setActiveTab(val as AdminTab)}
      >
        <TabList>
          <Tab value="overview">Overview</Tab>
          <Tab value="pipeline">
            <TabIcon>
              <Workflow size={14} />
            </TabIcon>
            Pipeline Configuration
          </Tab>
        </TabList>

        <TabPanels>
          <TabPanel value="overview">
            <TabContent>
              <SettingsGrid>
                {overviewItems.map((item) => {
                  const IconComponent = item.icon;
                  return (
                    <SettingsCard
                      key={item.id}
                      data-testid={`settings-card-${item.id}`}
                      $disabled={item.comingSoon}
                      onClick={() => handleCardClick(item)}
                    >
                      <CardIconWrapper $gradient={item.gradient}>
                        <IconComponent size={24} color="white" />
                      </CardIconWrapper>
                      <CardTitle>
                        {item.title}
                        {item.comingSoon && (
                          <ComingSoonBadge>Coming Soon</ComingSoonBadge>
                        )}
                      </CardTitle>
                      <CardDescription>{item.description}</CardDescription>
                    </SettingsCard>
                  );
                })}
              </SettingsGrid>
            </TabContent>
          </TabPanel>

          <TabPanel value="pipeline">
            <TabContent>
              <SystemSettings />
            </TabContent>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Container>
  );
};

export default GlobalSettingsPanel;
