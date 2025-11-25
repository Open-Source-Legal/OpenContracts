/**
 * User Profile View Component
 *
 * Issue: #611 - Create User Profile Page with badge display and stats
 * Epic: #572 - Social Features Epic
 *
 * Displays comprehensive user profile including:
 * - User information and avatar
 * - Earned badges
 * - Contribution statistics
 * - Recent activity
 * - Edit profile button (for own profile)
 */

import React from "react";
import styled from "styled-components";
import { User, Settings, TrendingUp } from "lucide-react";
import { Container, Button } from "semantic-ui-react";
import { UserBadges } from "../components/badges/UserBadges";
import { UserProfileReputation } from "../components/threads/UserProfileReputation";
import { UserStats } from "../components/profile/UserStats";
import { RecentActivity } from "../components/profile/RecentActivity";
import { showUserSettingsModal } from "../graphql/cache";
import { color } from "../theme/colors";

// Outer scroll container with proper overflow handling
const ProfileContainer = styled.div`
  width: 100%;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;

  /* Custom scrollbar for webkit browsers */
  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: ${color.N2};
  }

  &::-webkit-scrollbar-thumb {
    background: ${color.N5};
    border-radius: 4px;
    transition: background 0.2s;

    &:hover {
      background: ${color.N6};
    }
  }
`;

// Inner content with proper max-width and padding
const ProfileContent = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 3rem 2rem;
  min-height: 100%;

  @media (max-width: 768px) {
    padding: 2rem 1.5rem;
  }

  @media (max-width: 480px) {
    padding: 1.5rem 1rem;
  }
`;

const ProfileHeader = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 2.5rem;
  padding: 2.5rem;
  background: white;
  border: 1px solid ${color.N3};
  border-radius: 20px;
  margin-bottom: 2.5rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 4px 16px rgba(0, 0, 0, 0.02);
  transition: box-shadow 0.3s ease;

  &:hover {
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06), 0 8px 24px rgba(0, 0, 0, 0.04);
  }

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: center;
    gap: 1.5rem;
    padding: 2rem;
    text-align: center;
  }

  @media (max-width: 480px) {
    padding: 1.5rem;
  }
`;

const Avatar = styled.div`
  width: 128px;
  height: 128px;
  border-radius: 50%;
  background: linear-gradient(135deg, ${color.B5} 0%, ${color.P5} 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 52px;
  font-weight: 600;
  color: white;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 8px 24px rgba(0, 0, 0, 0.06);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  letter-spacing: -0.02em;

  &:hover {
    transform: scale(1.02);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 0 12px 32px rgba(0, 0, 0, 0.08);
  }

  @media (max-width: 768px) {
    width: 112px;
    height: 112px;
    font-size: 44px;
  }

  @media (max-width: 480px) {
    width: 96px;
    height: 96px;
    font-size: 38px;
  }
`;

const ProfileInfo = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0; /* Prevent flex item overflow */
`;

const ProfileName = styled.h1`
  margin: 0;
  font-size: 36px;
  font-weight: 600;
  color: ${color.N10};
  letter-spacing: -0.03em;
  line-height: 1.2;

  @media (max-width: 768px) {
    font-size: 28px;
  }

  @media (max-width: 480px) {
    font-size: 24px;
  }
`;

const ProfileUsername = styled.div`
  font-size: 17px;
  color: ${color.N6};
  font-weight: 500;
  letter-spacing: -0.01em;

  @media (max-width: 480px) {
    font-size: 15px;
  }
`;

const ProfileEmail = styled.div`
  font-size: 15px;
  color: ${color.N5};
  margin-top: 0.25rem;

  @media (max-width: 480px) {
    font-size: 14px;
  }
`;

const ActionButtons = styled.div`
  display: flex;
  gap: 0.75rem;
  margin-top: 1.25rem;

  button {
    border-radius: 10px !important;
    font-weight: 500 !important;
    padding: 0.625rem 1.25rem !important;
    transition: all 0.2s ease !important;
    border: 1px solid ${color.N4} !important;

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
    }

    &:active {
      transform: translateY(0);
    }
  }

  @media (max-width: 768px) {
    width: 100%;
    justify-content: center;

    button {
      flex: 1;
    }
  }

  @media (max-width: 480px) {
    flex-direction: column;
  }
`;

const ContentGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;

  @media (min-width: 900px) {
    grid-template-columns: 1.75fr 1fr;
    gap: 2.5rem;
  }

  @media (max-width: 768px) {
    gap: 1.5rem;
  }
`;

const MainColumn = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2rem;
  min-width: 0; /* Prevent grid blowout */

  @media (max-width: 768px) {
    gap: 1.5rem;
  }
`;

const SideColumn = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2rem;
  min-width: 0; /* Prevent grid blowout */

  @media (max-width: 768px) {
    gap: 1.5rem;
  }
`;

const Section = styled.div`
  background: white;
  border: 1px solid ${color.N3};
  border-radius: 16px;
  padding: 2rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03), 0 2px 8px rgba(0, 0, 0, 0.02);
  transition: box-shadow 0.3s ease, transform 0.3s ease;
  overflow: hidden; /* Prevent content overflow */

  &:hover {
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(0, 0, 0, 0.03);
  }

  @media (max-width: 768px) {
    padding: 1.5rem;
  }

  @media (max-width: 480px) {
    padding: 1.25rem;
  }
`;

const SectionTitle = styled.h2`
  margin: 0 0 1.75rem 0;
  font-size: 19px;
  font-weight: 600;
  color: ${color.N10};
  display: flex;
  align-items: center;
  gap: 0.625rem;
  letter-spacing: -0.01em;

  svg {
    width: 20px;
    height: 20px;
    color: ${color.N7};
    flex-shrink: 0;
  }

  @media (max-width: 480px) {
    font-size: 17px;
    margin-bottom: 1.25rem;
  }
`;

export interface UserProfileProps {
  user: {
    id: string;
    username: string;
    slug: string;
    name: string;
    firstName: string;
    lastName: string;
    email: string;
    isProfilePublic: boolean;
    reputationGlobal: number;
    totalMessages: number;
    totalThreadsCreated: number;
    totalAnnotationsCreated: number;
    totalDocumentsUploaded: number;
  };
  isOwnProfile: boolean;
}

export const UserProfile: React.FC<UserProfileProps> = ({
  user,
  isOwnProfile,
}) => {
  // Get initials for avatar
  const getInitials = () => {
    if (user.firstName && user.lastName) {
      return `${user.firstName[0]}${user.lastName[0]}`.toUpperCase();
    }
    if (user.name) {
      const parts = user.name.split(" ");
      if (parts.length >= 2) {
        return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
      }
      return user.name.substring(0, 2).toUpperCase();
    }
    return user.username.substring(0, 2).toUpperCase();
  };

  const displayName =
    user.name ||
    `${user.firstName || ""} ${user.lastName || ""}`.trim() ||
    user.username;

  // Calculate recent change (placeholder - would need backend support for real data)
  const recentChange = 0; // TODO: Backend would need to track this

  return (
    <ProfileContainer>
      <ProfileContent>
        <ProfileHeader>
          <Avatar>{getInitials()}</Avatar>
          <ProfileInfo>
            <ProfileName>{displayName}</ProfileName>
            <ProfileUsername>@{user.username}</ProfileUsername>
            {isOwnProfile && user.email && (
              <ProfileEmail>{user.email}</ProfileEmail>
            )}
            {isOwnProfile && (
              <ActionButtons>
                <Button
                  icon
                  labelPosition="left"
                  onClick={() => showUserSettingsModal(true)}
                >
                  <Settings size={16} />
                  Edit Profile
                </Button>
              </ActionButtons>
            )}
          </ProfileInfo>
        </ProfileHeader>

        <ContentGrid>
          <MainColumn>
            {/* Badges Section */}
            <Section>
              <UserBadges userId={user.id} showTitle={true} title="Badges" />
            </Section>

            {/* Recent Activity Section */}
            <Section>
              <SectionTitle>
                <TrendingUp />
                Recent Activity
              </SectionTitle>
              <RecentActivity userId={user.id} />
            </Section>
          </MainColumn>

          <SideColumn>
            {/* Reputation Section */}
            <Section>
              <UserProfileReputation
                globalReputation={user.reputationGlobal}
                upvotesReceived={0} // TODO: Backend support needed
                downvotesReceived={0} // TODO: Backend support needed
                recentChange={recentChange}
                changePeriod="this week"
              />
            </Section>

            {/* Stats Section */}
            <Section>
              <SectionTitle>
                <User />
                Contribution Stats
              </SectionTitle>
              <UserStats
                totalMessages={user.totalMessages}
                totalThreads={user.totalThreadsCreated}
                totalAnnotations={user.totalAnnotationsCreated}
                totalDocuments={user.totalDocumentsUploaded}
              />
            </Section>
          </SideColumn>
        </ContentGrid>
      </ProfileContent>
    </ProfileContainer>
  );
};
