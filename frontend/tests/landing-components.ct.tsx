// Playwright Component Tests for Landing Page Components
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { CompactLeaderboard } from "../src/components/landing/CompactLeaderboard";
import { CallToAction } from "../src/components/landing/CallToAction";
import { DiscoveryLanding } from "../src/views/DiscoveryLanding";
import { LandingTestWrapper } from "./LandingTestWrapper";
import { GET_DISCOVERY_DATA } from "../src/graphql/landing-queries";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

// Mock data
const mockCommunityStats = {
  totalUsers: 1234,
  totalThreads: 234,
  totalMessages: 5678,
  totalAnnotations: 12345,
  activeUsersThisWeek: 89,
  activeUsersThisMonth: 234,
};

const mockCorpuses = [
  {
    node: {
      id: "Q29ycHVzVHlwZTox",
      slug: "legal-contracts",
      title: "Legal Contracts Collection",
      description: "A comprehensive collection of legal contracts for analysis",
      icon: null,
      isPublic: true,
      created: "2024-01-15T10:30:00Z",
      creator: {
        id: "VXNlclR5cGU6MQ==",
        username: "testuser",
        slug: "testuser",
      },
      documents: { totalCount: 150 },
      documentCount: 150,
      annotations: { totalCount: 5000 },
      engagementMetrics: {
        totalThreads: 25,
        totalMessages: 150,
        uniqueContributors: 12,
      },
    },
  },
  {
    node: {
      id: "Q29ycHVzVHlwZToy",
      slug: "research-papers",
      title: "Research Papers Archive",
      description: "Academic research papers on various topics",
      icon: null,
      isPublic: true,
      created: "2024-02-01T14:00:00Z",
      creator: {
        id: "VXNlclR5cGU6Mg==",
        username: "researcher",
        slug: "researcher",
      },
      documents: { totalCount: 300 },
      documentCount: 300,
      annotations: { totalCount: 8000 },
      engagementMetrics: {
        totalThreads: 45,
        totalMessages: 320,
        uniqueContributors: 28,
      },
    },
  },
];

const mockDiscussions = [
  {
    node: {
      id: "Q29udmVyc2F0aW9uVHlwZTox",
      title: "Discussion about contract clauses",
      description: "Let's analyze the key clauses in this contract",
      createdAt: "2024-03-10T10:00:00Z",
      updatedAt: "2024-03-10T15:30:00Z",
      isPinned: true,
      isLocked: false,
      creator: {
        id: "VXNlclR5cGU6MQ==",
        username: "testuser",
      },
      chatMessages: { totalCount: 15 },
      chatWithCorpus: {
        id: "Q29ycHVzVHlwZTox",
        title: "Legal Contracts Collection",
        slug: "legal-contracts",
        creator: { slug: "testuser" },
      },
    },
  },
  {
    node: {
      id: "Q29udmVyc2F0aW9uVHlwZToy",
      title: "Research methodology questions",
      description:
        "Questions about the research methodology used in this paper",
      createdAt: "2024-03-09T08:00:00Z",
      updatedAt: "2024-03-09T16:45:00Z",
      isPinned: false,
      isLocked: false,
      creator: {
        id: "VXNlclR5cGU6Mg==",
        username: "researcher",
      },
      chatMessages: { totalCount: 8 },
      chatWithCorpus: {
        id: "Q29ycHVzVHlwZToy",
        title: "Research Papers Archive",
        slug: "research-papers",
        creator: { slug: "researcher" },
      },
    },
  },
];

const mockLeaderboard = [
  {
    id: "VXNlclR5cGU6MQ==",
    username: "topcontributor",
    slug: "topcontributor",
    reputationGlobal: 1500,
    totalMessages: 250,
    totalThreadsCreated: 35,
    totalAnnotationsCreated: 500,
    badges: {
      edges: [
        {
          node: {
            badge: {
              id: "QmFkZ2VUeXBlOjE=",
              name: "Expert",
              icon: "🏆",
              color: "#FFD700",
            },
          },
        },
      ],
    },
  },
  {
    id: "VXNlclR5cGU6Mg==",
    username: "activeuser",
    slug: "activeuser",
    reputationGlobal: 1200,
    totalMessages: 180,
    totalThreadsCreated: 20,
    totalAnnotationsCreated: 350,
    badges: {
      edges: [],
    },
  },
];

const mockDiscoveryData = {
  corpuses: {
    edges: mockCorpuses,
    pageInfo: { hasNextPage: false, endCursor: null },
  },
  conversations: {
    edges: mockDiscussions,
    pageInfo: { hasNextPage: false, endCursor: null },
    totalCount: 2,
  },
  communityStats: mockCommunityStats,
  globalLeaderboard: mockLeaderboard,
};

// ============================================================================
// CompactLeaderboard Tests
// ============================================================================
test.describe("CompactLeaderboard Component", () => {
  test("should render contributor rows with usernames", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <LandingTestWrapper>
        <CompactLeaderboard contributors={mockLeaderboard} loading={false} />
      </LandingTestWrapper>
    );

    // Check contributor names are displayed
    await expect(page.locator("text=topcontributor")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=activeuser")).toBeVisible();

    await docScreenshot(page, "landing--leaderboard--with-data", {
      element: component,
    });
    await releaseScreenshot(page, "v3.0.0.b3", "leaderboard", {
      element: component,
    });

    await component.unmount();
  });

  test("should display reputation scores", async ({ mount, page }) => {
    const component = await mount(
      <LandingTestWrapper>
        <CompactLeaderboard contributors={mockLeaderboard} loading={false} />
      </LandingTestWrapper>
    );

    // Check reputation values
    await expect(page.locator("text=1500")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=1200")).toBeVisible();

    await component.unmount();
  });

  test("should show View Full Leaderboard button", async ({ mount, page }) => {
    const component = await mount(
      <LandingTestWrapper>
        <CompactLeaderboard contributors={mockLeaderboard} loading={false} />
      </LandingTestWrapper>
    );

    await expect(page.locator("text=View Full Leaderboard")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });
});

// ============================================================================
// CallToAction Tests
// ============================================================================
test.describe("CallToAction Component", () => {
  test("should render CTA for anonymous users", async ({ mount, page }) => {
    const component = await mount(
      <LandingTestWrapper>
        <CallToAction isAuthenticated={false} />
      </LandingTestWrapper>
    );

    // Check CTA content
    await expect(page.locator("text=Ready to dive in?")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("text=Get Started Free")).toBeVisible();

    // Check features
    await expect(page.locator("text=Open Source & Free")).toBeVisible();
    await expect(page.locator("text=AI-Powered Analysis")).toBeVisible();

    // Allow framer-motion animations to fully settle before screenshot
    await page.waitForTimeout(1000);

    // Doc screenshot: call-to-action section for anonymous users
    await docScreenshot(page, "landing--call-to-action--anonymous", {
      element: component,
    });

    await component.unmount();
  });

  test("should not render for authenticated users", async ({ mount, page }) => {
    const component = await mount(
      <LandingTestWrapper>
        <CallToAction isAuthenticated={true} />
      </LandingTestWrapper>
    );

    // CTA should not be visible for authenticated users
    await expect(page.locator("text=Ready to dive in?")).not.toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

// ============================================================================
// DiscoveryLanding Integration Tests
// ============================================================================
test.describe("DiscoveryLanding Page", () => {
  test("should render hero section", async ({ mount, page }) => {
    const discoveryDataMock = {
      request: {
        query: GET_DISCOVERY_DATA,
        variables: {
          corpusLimit: 6,
          discussionLimit: 5,
          leaderboardLimit: 6,
          conversationType: "THREAD",
        },
      },
      result: {
        data: mockDiscoveryData,
      },
    };

    const component = await mount(
      <LandingTestWrapper mocks={[discoveryDataMock]}>
        <DiscoveryLanding isAuthenticatedOverride={false} />
      </LandingTestWrapper>
    );

    // Check hero section - updated text after redesign
    await expect(page.locator("text=The open platform for")).toBeVisible({
      timeout: 15000,
    });

    // Doc screenshot: full discovery landing page integration
    await docScreenshot(page, "landing--discovery-page--anonymous", {
      fullPage: true,
    });
    await releaseScreenshot(page, "v3.0.0.b3", "landing-page", {
      fullPage: true,
    });

    await component.unmount();
  });
});
