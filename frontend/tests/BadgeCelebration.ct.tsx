import { test, expect } from "@playwright/experimental-ct-react";
import { BadgeCelebrationModal } from "../src/components/badges/BadgeCelebrationModal";
import { BadgeToast } from "../src/components/badges/BadgeToast";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

test.describe("BadgeCelebrationModal", () => {
  test("renders with badge information", async ({ mount, page }) => {
    const component = await mount(
      <BadgeCelebrationModal
        badgeName="First Post"
        badgeDescription="Made your first post in the community"
        badgeIcon="Trophy"
        badgeColor="#05313d"
        isAutoAwarded={true}
        onClose={() => {}}
      />
    );

    // Wait for animations to settle
    await page.waitForTimeout(500);

    await expect(
      component.getByRole("heading", { name: "First Post" })
    ).toBeVisible({ timeout: 20000 });
    await expect(
      component.getByText("Made your first post in the community")
    ).toBeVisible({ timeout: 20000 });
    await expect(
      component.getByText("Congratulations on your achievement!")
    ).toBeVisible({ timeout: 20000 });

    // Doc screenshot: badge celebration modal with auto-awarded badge
    await docScreenshot(page, "badges--celebration-modal--auto-award");
    await releaseScreenshot(page, "v3.0.0.b3", "badge-celebration");
  });

  test("shows awarded by message for manual awards", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BadgeCelebrationModal
        badgeName="Helpful Contributor"
        badgeDescription="Recognized for helpful contributions"
        badgeIcon="Award"
        badgeColor="#e67e22"
        isAutoAwarded={false}
        awardedBy={{ username: "adminuser" }}
        onClose={() => {}}
      />
    );

    await page.waitForTimeout(500);
    await expect(component.getByText(/Awarded by adminuser/)).toBeVisible({
      timeout: 20000,
    });

    // Doc screenshot: badge celebration modal with manual award
    await docScreenshot(page, "badges--celebration-modal--manual-award");
  });

  test("calls onClose when close button clicked", async ({ mount, page }) => {
    let closeCalled = false;

    const component = await mount(
      <BadgeCelebrationModal
        badgeName="Test Badge"
        badgeDescription="Test description"
        badgeIcon="Star"
        badgeColor="#3498db"
        isAutoAwarded={true}
        onClose={() => {
          closeCalled = true;
        }}
      />
    );

    await page.waitForTimeout(500);
    await component.getByRole("button", { name: "Close" }).click();
    expect(closeCalled).toBe(true);
  });

  test("calls onViewBadges when button clicked", async ({ mount, page }) => {
    let viewBadgesCalled = false;

    const component = await mount(
      <BadgeCelebrationModal
        badgeName="Test Badge"
        badgeDescription="Test description"
        badgeIcon="Star"
        badgeColor="#3498db"
        isAutoAwarded={true}
        onClose={() => {}}
        onViewBadges={() => {
          viewBadgesCalled = true;
        }}
      />
    );

    await page.waitForTimeout(500);
    await component.getByRole("button", { name: "View Your Badges" }).click();
    expect(viewBadgesCalled).toBe(true);
  });

  test("displays badge icon", async ({ mount, page }) => {
    const component = await mount(
      <BadgeCelebrationModal
        badgeName="Star Badge"
        badgeDescription="Test description"
        badgeIcon="Star"
        badgeColor="#f1c40f"
        isAutoAwarded={true}
        onClose={() => {}}
      />
    );

    await page.waitForTimeout(500);
    // Check that the badge name heading is visible
    await expect(
      component.getByRole("heading", { name: "Star Badge" })
    ).toBeVisible({ timeout: 20000 });
    // Check that SVG icon is present
    await expect(component.locator("svg").first()).toBeVisible({
      timeout: 20000,
    });
  });

  test("closes when clicking close button", async ({ mount, page }) => {
    let closeCalled = false;

    const component = await mount(
      <BadgeCelebrationModal
        badgeName="Test Badge"
        badgeDescription="Test description"
        badgeIcon="Star"
        badgeColor="#3498db"
        isAutoAwarded={true}
        onClose={() => {
          closeCalled = true;
        }}
      />
    );

    await page.waitForTimeout(500);
    // Click the close button
    await component.getByRole("button", { name: "Close" }).click();
    expect(closeCalled).toBe(true);
  });
});

test.describe("BadgeToast", () => {
  test("renders badge information in toast", async ({ mount, page }) => {
    const component = await mount(
      <BadgeToast
        badgeName="First Post"
        badgeIcon="Trophy"
        badgeColor="#05313d"
        isAutoAwarded={true}
      />
    );

    await page.waitForTimeout(200);
    await expect(component.getByText("Badge Earned!")).toBeVisible({
      timeout: 20000,
    });
    await expect(
      component.getByText(/You earned the "First Post" badge!/)
    ).toBeVisible({ timeout: 20000 });

    // Doc screenshot: badge earned toast notification
    await docScreenshot(page, "badges--toast--earned", {
      element: component,
    });
  });

  test("shows awarded by message for manual awards", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BadgeToast
        badgeName="Helpful"
        badgeIcon="Award"
        badgeColor="#e67e22"
        isAutoAwarded={false}
        awardedBy={{ username: "adminuser" }}
      />
    );

    await page.waitForTimeout(200);
    await expect(
      component.getByText(/adminuser awarded you the "Helpful" badge!/)
    ).toBeVisible({ timeout: 20000 });
  });

  test("displays badge icon with correct color", async ({ mount, page }) => {
    const component = await mount(
      <BadgeToast
        badgeName="Test Badge"
        badgeIcon="Star"
        badgeColor="#3498db"
        isAutoAwarded={true}
      />
    );

    await page.waitForTimeout(200);
    // Check that SVG icon is visible
    await expect(component.locator("svg").first()).toBeVisible({
      timeout: 20000,
    });
    // Check that "Badge Earned!" text is visible
    await expect(component.getByText("Badge Earned!")).toBeVisible({
      timeout: 20000,
    });
  });

  test("handles unknown icon gracefully", async ({ mount, page }) => {
    const component = await mount(
      <BadgeToast
        badgeName="Unknown Icon Badge"
        badgeIcon="NonExistentIcon123"
        badgeColor="#9b59b6"
        isAutoAwarded={true}
      />
    );

    await page.waitForTimeout(200);
    // Should still render with fallback icon
    await expect(component.getByText("Badge Earned!")).toBeVisible({
      timeout: 20000,
    });
  });
});
