import React from "react";
import { useNavigate } from "react-router-dom";
import { Header } from "semantic-ui-react";
import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import { Settings, Trophy, Bot, Cog, Users, LucideIcon } from "lucide-react";

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
  margin-bottom: 2rem;

  @media (max-width: 768px) {
    margin-bottom: 1.5rem;
    text-align: center;
  }
`;

const PageTitle = styled(Header)`
  &.ui.header {
    margin-bottom: 0.5rem;
    color: #1e293b;

    @media (max-width: 768px) {
      font-size: 1.5rem !important;
    }

    @media (max-width: 480px) {
      font-size: 1.3rem !important;
    }
  }
`;

const PageDescription = styled.p`
  color: #64748b;
  font-size: 1rem;
  margin: 0;

  @media (max-width: 768px) {
    font-size: 0.9rem;
  }
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

const SettingsCard = styled(Card)`
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  /* Disable hover transforms on touch devices */
  @media (hover: none) {
    &:hover {
      transform: none;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    &:active {
      transform: scale(0.98);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
    }
  }
`;

const SettingsCardBody = styled(CardBody)`
  padding: 1.5rem;

  @media (max-width: 768px) {
    padding: 1.25rem;
  }

  @media (max-width: 480px) {
    padding: 1rem;
  }
`;

const CardIcon = styled.div<{ $color: string }>`
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: ${(props) => props.$color};
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;

  @media (max-width: 768px) {
    width: 44px;
    height: 44px;
    margin-bottom: 0.75rem;
  }

  i.icon {
    color: white;
    margin: 0;
  }
`;

const CardTitle = styled.h3`
  font-size: 1.125rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.5rem 0;

  @media (max-width: 768px) {
    font-size: 1rem;
  }
`;

const CardDescription = styled.p`
  font-size: 0.875rem;
  color: #64748b;
  margin: 0;
  line-height: 1.5;

  @media (max-width: 768px) {
    font-size: 0.8rem;
  }
`;

const ComingSoonBadge = styled.span`
  display: inline-block;
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

interface SettingItem {
  id: string;
  title: string;
  description: string;
  Icon: LucideIcon;
  color: string;
  route?: string;
  comingSoon?: boolean;
}

const settingsItems: SettingItem[] = [
  {
    id: "badges",
    title: "Badge Management",
    description:
      "Create and manage badges that can be awarded to users for achievements and contributions.",
    Icon: Trophy,
    color: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
    route: "/admin/badges",
  },
  {
    id: "global-agents",
    title: "Global Agents",
    description:
      "Configure global AI agents available across all corpuses for document and corpus analysis.",
    Icon: Bot,
    color: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
    route: "/admin/agents",
  },
  {
    id: "system-settings",
    title: "System Settings",
    description:
      "Configure system-wide settings including defaults, limits, and feature flags.",
    Icon: Cog,
    color: "linear-gradient(135deg, #64748b 0%, #475569 100%)",
    comingSoon: true,
  },
  {
    id: "user-management",
    title: "User Management",
    description:
      "View and manage user accounts, permissions, and access controls.",
    Icon: Users,
    color: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
    comingSoon: true,
  },
];

export const GlobalSettingsPanel: React.FC = () => {
  const navigate = useNavigate();

  const handleCardClick = (item: SettingItem) => {
    if (item.route && !item.comingSoon) {
      navigate(item.route);
    }
  };

  return (
    <Container>
      <PageHeader>
        <PageTitle as="h1">
          <Settings
            size={24}
            style={{ marginRight: "0.5em", verticalAlign: "middle" }}
          />{" "}
          Admin Settings
        </PageTitle>
        <PageDescription>
          Manage global settings, configurations, and administrative features
          for OpenContracts.
        </PageDescription>
      </PageHeader>

      <SettingsGrid>
        {settingsItems.map((item) => (
          <SettingsCard
            key={item.id}
            onClick={() => handleCardClick(item)}
            style={{ opacity: item.comingSoon ? 0.7 : 1 }}
          >
            <SettingsCardBody>
              <CardIcon $color={item.color}>
                <item.Icon size={24} color="white" />
              </CardIcon>
              <CardTitle>
                {item.title}
                {item.comingSoon && (
                  <ComingSoonBadge>Coming Soon</ComingSoonBadge>
                )}
              </CardTitle>
              <CardDescription>{item.description}</CardDescription>
            </SettingsCardBody>
          </SettingsCard>
        ))}
      </SettingsGrid>
    </Container>
  );
};

export default GlobalSettingsPanel;
