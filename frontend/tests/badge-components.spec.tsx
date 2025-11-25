// Playwright Component Test for Badge System
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedProvider } from "@apollo/client/testing";
import { Badge } from "../src/components/badges/Badge";
import { UserBadges } from "../src/components/badges/UserBadges";
import { BadgeManagement } from "../src/components/badges/BadgeManagement";
import { AwardBadgeModal } from "../src/components/badges/AwardBadgeModal";
import { GET_BADGES, GET_USER_BADGES } from "../src/graphql/queries";
import {
  CREATE_BADGE,
  DELETE_BADGE,
  AWARD_BADGE,
} from "../src/graphql/mutations";

const mockGlobalBadge = {
  id: "QmFkZ2VUeXBlOjE=",
  name: "Community Champion",
  description: "Awarded for exceptional community contributions",
  icon: "Trophy",
  badgeType: "GLOBAL",
  color: "#FFD700",
  corpus: null,
  isAutoAwarded: false,
  criteriaConfig: null,
};

const mockCorpusBadge = {
  id: "QmFkZ2VUeXBlOjI=",
  name: "Corpus Expert",
  description: "Expert in this corpus",
  icon: "Award",
  badgeType: "CORPUS",
  color: "#0066cc",
  corpus: {
    id: "Q29ycHVzVHlwZTox",
    title: "Test Corpus",
  },
  isAutoAwarded: false,
  criteriaConfig: null,
};

const mockUserBadge = {
  id: "VXNlckJhZGdlVHlwZTox",
  badge: mockGlobalBadge,
  awardedAt: "2024-01-15T10:30:00Z",
  awardedBy: {
    id: "VXNlclR5cGU6MQ==",
    username: "admin",
  },
  corpus: null,
};

const mockUser = {
  id: "VXNlclR5cGU6Mg==",
  username: "testuser",
};

test.describe("Badge Component", () => {
  test("should render a global badge with correct styling", async ({
    mount,
    page,
  }) => {
    const component = await mount(<Badge badge={mockGlobalBadge} />);

    // Check badge is visible
    await expect(page.locator('[data-testid="badge"]')).toBeVisible();

    // Check icon is rendered
    await expect(page.locator("svg")).toBeVisible();

    // Check badge name is in tooltip
    const badge = page.locator('[data-testid="badge"]');
    await badge.hover();
    await expect(page.locator("text=Community Champion")).toBeVisible({
      timeout: 2000,
    });

    await component.unmount();
  });

  test("should render a corpus badge with corpus info", async ({
    mount,
    page,
  }) => {
    const component = await mount(<Badge badge={mockCorpusBadge} />);

    await expect(page.locator('[data-testid="badge"]')).toBeVisible();

    // Hover to see tooltip with corpus info
    const badge = page.locator('[data-testid="badge"]');
    await badge.hover();
    await expect(page.locator("text=Test Corpus")).toBeVisible({
      timeout: 2000,
    });

    await component.unmount();
  });

  test("should render different badge sizes", async ({ mount, page }) => {
    const smallBadge = await mount(
      <Badge badge={mockGlobalBadge} size="small" />
    );
    await expect(page.locator('[data-testid="badge"]')).toBeVisible();
    await smallBadge.unmount();

    const mediumBadge = await mount(
      <Badge badge={mockGlobalBadge} size="medium" />
    );
    await expect(page.locator('[data-testid="badge"]')).toBeVisible();
    await mediumBadge.unmount();

    const largeBadge = await mount(
      <Badge badge={mockGlobalBadge} size="large" />
    );
    await expect(page.locator('[data-testid="badge"]')).toBeVisible();
    await largeBadge.unmount();
  });
});

test.describe("UserBadges Component", () => {
  test("should display user badges from query", async ({ mount, page }) => {
    const getUserBadgesMock = {
      request: {
        query: GET_USER_BADGES,
        variables: {
          userId: "VXNlclR5cGU6Mg==",
        },
      },
      result: {
        data: {
          userBadges: {
            edges: [
              {
                node: mockUserBadge,
              },
            ],
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[getUserBadgesMock]} addTypename={false}>
        <UserBadges userId="VXNlclR5cGU6Mg==" />
      </MockedProvider>
    );

    // Wait for badges to load
    await expect(page.locator('[data-testid="badge"]')).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });

  test("should show empty state when user has no badges", async ({
    mount,
    page,
  }) => {
    const emptyBadgesMock = {
      request: {
        query: GET_USER_BADGES,
        variables: {
          userId: "VXNlclR5cGU6Mg==",
        },
      },
      result: {
        data: {
          userBadges: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[emptyBadgesMock]} addTypename={false}>
        <UserBadges userId="VXNlclR5cGU6Mg==" />
      </MockedProvider>
    );

    // Check for empty state message
    await expect(page.locator("text=No badges yet")).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });

  test("should show loading state", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <UserBadges userId="VXNlclR5cGU6Mg==" />
      </MockedProvider>
    );

    // Should show loading indicator
    await expect(page.locator("text=Loading badges...")).toBeVisible({
      timeout: 1000,
    });

    await component.unmount();
  });
});

test.describe("BadgeManagement Component", () => {
  test("should display list of badges", async ({ mount, page }) => {
    const getBadgesMock = {
      request: {
        query: GET_BADGES,
        variables: {},
      },
      result: {
        data: {
          badges: {
            edges: [{ node: mockGlobalBadge }, { node: mockCorpusBadge }],
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[getBadgesMock]} addTypename={false}>
        <BadgeManagement />
      </MockedProvider>
    );

    // Wait for badges to load in table
    await expect(page.locator("text=Community Champion")).toBeVisible({
      timeout: 3000,
    });
    await expect(page.locator("text=Corpus Expert")).toBeVisible();

    await component.unmount();
  });

  test("should open create badge modal", async ({ mount, page }) => {
    const getBadgesMock = {
      request: {
        query: GET_BADGES,
        variables: {},
      },
      result: {
        data: {
          badges: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[getBadgesMock]} addTypename={false}>
        <BadgeManagement />
      </MockedProvider>
    );

    // Click create badge button
    await page.locator('button:has-text("Create Badge")').click();

    // Modal should open
    await expect(page.locator("text=Create New Badge")).toBeVisible();

    await component.unmount();
  });

  test("should handle badge deletion", async ({ mount, page }) => {
    const getBadgesMock = {
      request: {
        query: GET_BADGES,
        variables: {},
      },
      result: {
        data: {
          badges: {
            edges: [{ node: mockGlobalBadge }],
          },
        },
      },
    };

    const deleteBadgeMock = {
      request: {
        query: DELETE_BADGE,
        variables: {
          badgeId: "QmFkZ2VUeXBlOjE=",
        },
      },
      result: {
        data: {
          deleteBadge: {
            ok: true,
            message: "Badge deleted successfully",
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider
        mocks={[getBadgesMock, deleteBadgeMock]}
        addTypename={false}
      >
        <BadgeManagement />
      </MockedProvider>
    );

    // Wait for badge to load
    await expect(page.locator("text=Community Champion")).toBeVisible({
      timeout: 3000,
    });

    // Click delete button
    await page.locator('button[aria-label="Delete"]').first().click();

    // Confirm deletion
    await page.locator('button:has-text("Delete")').click();

    await component.unmount();
  });
});

test.describe("AwardBadgeModal Component", () => {
  test("should display available badges", async ({ mount, page }) => {
    const getBadgesMock = {
      request: {
        query: GET_BADGES,
        variables: {},
      },
      result: {
        data: {
          badges: {
            edges: [{ node: mockGlobalBadge }, { node: mockCorpusBadge }],
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider mocks={[getBadgesMock]} addTypename={false}>
        <AwardBadgeModal
          open={true}
          onClose={() => {}}
          userId="VXNlclR5cGU6Mg=="
        />
      </MockedProvider>
    );

    // Modal should be visible
    await expect(page.locator("text=Award Badge")).toBeVisible();

    // Badge dropdown should load
    await expect(page.locator("text=Select Badge")).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });

  test("should handle badge awarding", async ({ mount, page }) => {
    const getBadgesMock = {
      request: {
        query: GET_BADGES,
        variables: {},
      },
      result: {
        data: {
          badges: {
            edges: [{ node: mockGlobalBadge }],
          },
        },
      },
    };

    const awardBadgeMock = {
      request: {
        query: AWARD_BADGE,
        variables: {
          badgeId: "QmFkZ2VUeXBlOjE=",
          userId: "VXNlclR5cGU6Mg==",
          corpusId: undefined,
        },
      },
      result: {
        data: {
          awardBadge: {
            ok: true,
            message: "Badge awarded successfully",
            userBadge: mockUserBadge,
          },
        },
      },
    };

    const component = await mount(
      <MockedProvider
        mocks={[getBadgesMock, awardBadgeMock]}
        addTypename={false}
      >
        <AwardBadgeModal
          open={true}
          onClose={() => {}}
          userId="VXNlclR5cGU6Mg=="
        />
      </MockedProvider>
    );

    // Wait for modal to load
    await expect(page.locator("text=Award Badge")).toBeVisible();

    // Select badge
    await page.locator('div[role="listbox"]').click();
    await page.locator("text=Community Champion").click();

    // Click award button
    await page.locator('button:has-text("Award Badge")').click();

    await component.unmount();
  });

  test("should close on cancel", async ({ mount, page }) => {
    const getBadgesMock = {
      request: {
        query: GET_BADGES,
        variables: {},
      },
      result: {
        data: {
          badges: {
            edges: [],
          },
        },
      },
    };

    let closed = false;
    const component = await mount(
      <MockedProvider mocks={[getBadgesMock]} addTypename={false}>
        <AwardBadgeModal
          open={true}
          onClose={() => {
            closed = true;
          }}
          userId="VXNlclR5cGU6Mg=="
        />
      </MockedProvider>
    );

    // Click cancel
    await page.locator('button:has-text("Cancel")').click();

    await component.unmount();
  });
});
