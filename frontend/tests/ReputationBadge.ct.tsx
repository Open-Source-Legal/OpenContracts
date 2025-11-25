import { test, expect } from "@playwright/experimental-ct-react";
import { ReputationBadge } from "../src/components/threads/ReputationBadge";

test.describe("ReputationBadge", () => {
  test("renders basic reputation badge", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={150} showTooltip={false} />
    );

    await expect(page.getByText("150")).toBeVisible();
  });

  test("formats large numbers with k suffix", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={1500} showTooltip={false} />
    );

    await expect(page.getByText("1.5k")).toBeVisible();
  });

  test("formats very large numbers", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={15000} showTooltip={false} />
    );

    await expect(page.getByText("15k")).toBeVisible();
  });

  test("shows icon when showIcon is true", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={150} showIcon={true} showTooltip={false} />
    );

    // Check for Award icon (Lucide React)
    const icon = page.locator("svg");
    await expect(icon).toBeVisible();
  });

  test("hides icon when showIcon is false", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={150} showIcon={false} showTooltip={false} />
    );

    const icon = page.locator("svg");
    await expect(icon).not.toBeVisible();
  });

  test("shows custom label", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge
        reputation={150}
        label="Global"
        showIcon={false}
        showTooltip={false}
      />
    );

    await expect(page.getByText("Global:")).toBeVisible();
    await expect(page.getByText("150")).toBeVisible();
  });

  test("renders small size", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge
        reputation={150}
        size="small"
        showIcon={false}
        showTooltip={false}
      />
    );
  });

  test("renders large size", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge
        reputation={150}
        size="large"
        showIcon={false}
        showTooltip={false}
      />
    );
  });

  test("shows tooltip on hover with breakdown", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge
        reputation={250}
        breakdown={{
          total: 250,
          fromUpvotes: 200,
          fromDownvotes: -20,
          fromAcceptedAnswers: 50,
          fromBadges: 20,
        }}
        showIcon={false}
        showTooltip={true}
      />
    );

    // Hover over badge (the reputation text)
    await page.getByText("250").hover();

    // Wait for tooltip
    await page.waitForTimeout(200);

    // Check tooltip content
    await expect(page.getByText("Reputation Breakdown")).toBeVisible();
    await expect(page.getByText("+200", { exact: true })).toBeVisible();
    await expect(page.getByText("-20", { exact: true })).toBeVisible();
    await expect(page.getByText("+50", { exact: true })).toBeVisible();
    await expect(page.getByText("+20", { exact: true })).toBeVisible();
  });

  test("shows corpus reputation in tooltip", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge
        reputation={250}
        breakdown={{
          total: 250,
          corpusReputation: 100,
          fromUpvotes: 150,
        }}
        showIcon={false}
        showTooltip={true}
      />
    );

    // Hover over badge (the reputation text)
    await page.getByText("250").hover();

    // Wait for tooltip
    await page.waitForTimeout(200);

    await expect(page.getByText("Corpus Reputation")).toBeVisible();
    await expect(page.getByText("100")).toBeVisible();
  });

  test("does not show tooltip when showTooltip is false", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ReputationBadge
        reputation={250}
        breakdown={{
          total: 250,
          fromUpvotes: 200,
        }}
        showIcon={false}
        showTooltip={false}
      />
    );

    // Hover over badge
    await page.locator("body").hover();

    // Wait a bit
    await page.waitForTimeout(200);

    // Tooltip should not appear
    await expect(page.getByText("Reputation Breakdown")).not.toBeVisible();
  });

  test("does not show tooltip when no breakdown provided", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ReputationBadge reputation={250} showIcon={false} showTooltip={true} />
    );

    // Hover over badge
    await page.locator("body").hover();

    // Wait a bit
    await page.waitForTimeout(200);

    // Tooltip should not appear since no breakdown was provided
    await expect(page.getByText("Reputation Breakdown")).not.toBeVisible();
  });

  test("handles negative reputation", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={-50} showIcon={false} showTooltip={false} />
    );

    await expect(page.getByText("-50")).toBeVisible();
  });

  test("handles zero reputation", async ({ mount, page }) => {
    const component = await mount(
      <ReputationBadge reputation={0} showIcon={false} showTooltip={false} />
    );

    await expect(page.getByText("0")).toBeVisible();
  });
});
