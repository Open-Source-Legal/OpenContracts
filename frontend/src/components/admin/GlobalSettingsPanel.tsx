import React from "react";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import {
  Trophy,
  Bot,
  Settings,
  Users,
  Upload,
  Tag,
  Activity,
  LucideIcon,
} from "lucide-react";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  OS_LEGAL_SPACING,
  OS_LEGAL_SHADOWS,
  OS_LEGAL_FONT_SIZES,
} from "../../assets/configurations/osLegalStyles";
import {
  MOBILE_VIEW_BREAKPOINT,
  TABLET_BREAKPOINT,
} from "../../assets/configurations/constants";

const PageContainer = styled.div`
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  overflow-y: auto;
  overflow-x: hidden;
`;

const ContentContainer = styled.main`
  max-width: ${OS_LEGAL_SPACING.pageMaxWidth};
  margin: 0 auto;
  padding: ${OS_LEGAL_SPACING.pagePaddingDesktop};

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: ${OS_LEGAL_SPACING.pagePaddingTablet};
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: ${OS_LEGAL_SPACING.pagePaddingMobile};
  }
`;

const HeroSection = styled.section`
  margin-bottom: ${OS_LEGAL_SPACING.sectionGapDesktop};

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    margin-bottom: ${OS_LEGAL_SPACING.sectionGapMobile};
    text-align: center;
  }
`;

const HeroTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: ${OS_LEGAL_FONT_SIZES.heroDesktop};
  font-weight: 400;
  line-height: 1.2;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 ${OS_LEGAL_SPACING.headingBottomGap};

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    font-size: ${OS_LEGAL_FONT_SIZES.heroTablet};
    justify-content: center;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: ${OS_LEGAL_FONT_SIZES.heroMobile};
  }
`;

const HeroSubtitle = styled.p`
  font-size: ${OS_LEGAL_FONT_SIZES.subtitleDesktop};
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0;
  max-width: ${OS_LEGAL_SPACING.subtitleMaxWidth};

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    font-size: ${OS_LEGAL_FONT_SIZES.subtitleMobile};
    margin: 0 auto;
  }
`;

const SettingsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(17.5rem, 1fr));
  gap: 1.5rem;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
    gap: 1rem;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }
`;

const SettingsCard = styled.div<{ $disabled?: boolean }>`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  box-shadow: ${OS_LEGAL_SHADOWS.card};
  padding: 1.5rem;
  cursor: ${({ $disabled }) => ($disabled ? "default" : "pointer")};
  opacity: ${({ $disabled }) => ($disabled ? 0.6 : 1)};
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;

  ${({ $disabled }) =>
    !$disabled &&
    `
    &:hover {
      transform: translateY(-2px);
      box-shadow: ${OS_LEGAL_SHADOWS.cardHover};
      border-color: ${OS_LEGAL_COLORS.borderHover};
    }

    @media (hover: none) {
      &:hover {
        transform: none;
        box-shadow: ${OS_LEGAL_SHADOWS.card};
        border-color: ${OS_LEGAL_COLORS.border};
      }

      &:active {
        transform: scale(0.98);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
      }
    }
  `}

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 1.25rem;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

const CardIconWrapper = styled.div<{ $gradient: string }>`
  width: 3rem;
  height: 3rem;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  background: ${({ $gradient }) => $gradient};
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    width: 2.75rem;
    height: 2.75rem;
    margin-bottom: 0.75rem;
  }
`;

const CardTitle = styled.h3`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: ${OS_LEGAL_FONT_SIZES.cardTitle};
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    font-size: ${OS_LEGAL_FONT_SIZES.cardTitleMobile};
  }
`;

const CardDescription = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: ${OS_LEGAL_FONT_SIZES.cardDescription};
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0;
  line-height: 1.5;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    font-size: ${OS_LEGAL_FONT_SIZES.cardDescriptionMobile};
  }
`;

const ComingSoonBadge = styled.span`
  display: inline-block;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: ${OS_LEGAL_FONT_SIZES.badge};
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.chartPurple};
  background: #f3e8ff;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  margin-left: 0.5rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
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
  icon: LucideIcon;
  gradient: string;
  route?: string;
  comingSoon?: boolean;
}

const settingsItems: SettingItem[] = [
  {
    id: "badges",
    title: "Badge Management",
    description:
      "Create and manage badges that can be awarded to users for achievements and contributions.",
    icon: Trophy,
    gradient: `linear-gradient(135deg, #f59e0b 0%, ${OS_LEGAL_COLORS.folderIcon} 100%)`,
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
    gradient: `linear-gradient(135deg, ${OS_LEGAL_COLORS.accent} 0%, ${OS_LEGAL_COLORS.accentHover} 100%)`,
    route: "/admin/worker-accounts",
  },
  {
    id: "ingestion-monitor",
    title: "Ingestion Monitor",
    description:
      "Diagnose document ingestion progress and failures, plus bulk and corpus-export import batch stats.",
    icon: Activity,
    gradient: `linear-gradient(135deg, ${OS_LEGAL_COLORS.danger} 0%, ${OS_LEGAL_COLORS.folderIcon} 100%)`,
    route: "/admin/ingestion",
  },
  {
    id: "corpus-categories",
    title: "Corpus Categories",
    description:
      "Create and manage the category tags (e.g. Case Law, Contracts) used to organize corpuses on the Discover page.",
    icon: Tag,
    gradient: `linear-gradient(135deg, ${OS_LEGAL_COLORS.chartPurple} 0%, ${OS_LEGAL_COLORS.agentPurple} 100%)`,
    route: "/admin/corpus-categories",
  },
  {
    id: "system-settings",
    title: "System Settings",
    description:
      "Configure system-wide pipeline settings including parsers, embedders, and document processing.",
    icon: Settings,
    gradient: `linear-gradient(135deg, ${OS_LEGAL_COLORS.textSecondary} 0%, ${OS_LEGAL_COLORS.textTertiary} 100%)`,
    route: "/system_settings",
  },
  {
    id: "user-management",
    title: "User Management",
    description:
      "View and manage user accounts, permissions, and access controls.",
    icon: Users,
    gradient: `linear-gradient(135deg, ${OS_LEGAL_COLORS.greenMedium} 0%, ${OS_LEGAL_COLORS.greenDark} 100%)`,
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
    <PageContainer>
      <ContentContainer>
        <HeroSection>
          <HeroTitle>
            <Settings size={32} color={OS_LEGAL_COLORS.accent} />
            Admin Settings
          </HeroTitle>
          <HeroSubtitle>
            Manage global settings, configurations, and administrative features
            for OpenContracts.
          </HeroSubtitle>
        </HeroSection>

        <SettingsGrid>
          {settingsItems.map((item) => {
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
      </ContentContainer>
    </PageContainer>
  );
};

export default GlobalSettingsPanel;
