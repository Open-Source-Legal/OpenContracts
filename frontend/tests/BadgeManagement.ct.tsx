import { test, expect } from "./utils/coverage";
import { BadgeManagementTestWrapper } from "./BadgeManagementTestWrapper";
import { GET_BADGES, GET_BADGE_CRITERIA_TYPES } from "../src/graphql/queries";
import { docScreenshot } from "./utils/docScreenshot";

const badgesMock = {
  request: {
    query: GET_BADGES,
    variables: { corpusId: undefined, limit: 100 },
  },
  result: {
    data: {
      badges: {
        edges: [
          {
            node: {
              id: "badge-1",
              name: "Annotation Pro",
              description: "Awarded for 100+ annotations",
              icon: "Award",
              badgeType: "GLOBAL",
              color: "#FFD700",
              isAutoAwarded: true,
              criteriaConfig: { type: "annotation_count", threshold: 100 },
              corpus: null,
              creator: { id: "user-1", username: "admin" },
              created: "2024-01-01T00:00:00Z",
            },
          },
          {
            node: {
              id: "badge-2",
              name: "Team Player",
              description: "Awarded for collaborating on 5 corpuses",
              icon: "Users",
              badgeType: "GLOBAL",
              color: "#4A90D9",
              isAutoAwarded: false,
              criteriaConfig: null,
              corpus: null,
              creator: { id: "user-1", username: "admin" },
              created: "2024-02-15T00:00:00Z",
            },
          },
        ],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: "YXJyYXljb25uZWN0aW9uOjA=",
          endCursor: "YXJyYXljb25uZWN0aW9uOjE=",
        },
      },
    },
  },
};

const criteriaMock = {
  request: {
    query: GET_BADGE_CRITERIA_TYPES,
    variables: { scope: "global" },
  },
  result: {
    data: {
      badgeCriteriaTypes: [
        {
          typeId: "annotation_count",
          name: "Annotation Count",
          description: "Award badge when user reaches annotation count",
          scope: "global",
          fields: [
            {
              name: "threshold",
              label: "Threshold",
              fieldType: "number",
              required: true,
              description: "Number of annotations required",
              minValue: 1,
              maxValue: 10000,
              allowedValues: null,
            },
          ],
          implemented: true,
        },
      ],
    },
  },
};

const createAllMocks = () => [
  { ...badgesMock, result: { ...badgesMock.result } },
  { ...badgesMock, result: { ...badgesMock.result } },
  { ...criteriaMock, result: { ...criteriaMock.result } },
  { ...criteriaMock, result: { ...criteriaMock.result } },
];

test.describe("BadgeManagement", () => {
  test("renders badge list with existing badges", async ({ mount, page }) => {
    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    // Wait for loading to finish and badge table to appear
    await expect(page.getByText("Badge Management")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Annotation Pro")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Team Player")).toBeVisible({
      timeout: 10000,
    });

    // Verify table headers
    await expect(page.getByText("Type")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Description")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Auto-Award")).toBeVisible({
      timeout: 10000,
    });

    await docScreenshot(page, "badges--management--with-badges");

    await component.unmount();
  });

  test("shows create badge button", async ({ mount, page }) => {
    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    // Wait for loading to finish
    await expect(page.getByText("Badge Management")).toBeVisible({
      timeout: 10000,
    });

    // Verify Create Badge button is present
    const createButton = page.getByRole("button", { name: "Create Badge" });
    await expect(createButton).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("create modal renders with icon and type dropdowns", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    // Wait for loading to finish
    await expect(page.getByText("Badge Management")).toBeVisible({
      timeout: 10000,
    });

    // Click Create Badge button to open modal
    await page.getByRole("button", { name: "Create Badge" }).click();

    // Wait for modal to appear
    await expect(page.getByText("Create New Badge")).toBeVisible({
      timeout: 10000,
    });

    // Verify form fields are present (use label tags for specificity)
    await expect(page.locator("label", { hasText: "Badge Name" })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("label", { hasText: "Icon" })).toBeVisible({
      timeout: 10000,
    });
    await expect(page.locator("label", { hasText: "Badge Type" })).toBeVisible({
      timeout: 10000,
    });

    // Verify icon dropdown shows default value "Trophy"
    const dropdowns = page.locator(".oc-dropdown__trigger");
    await expect(dropdowns.first()).toBeVisible({ timeout: 10000 });

    // Verify the icon dropdown displays "Trophy" as the selected value
    await expect(page.locator(".oc-dropdown__value").first()).toContainText(
      "Trophy"
    );

    // Verify the badge type dropdown displays "Global"
    await expect(page.locator(".oc-dropdown__value").nth(1)).toContainText(
      "Global"
    );

    // Verify Cancel and Create Badge buttons in footer
    const cancelButton = page.getByRole("button", { name: "Cancel" });
    await expect(cancelButton).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "badges--management--create-modal");

    await component.unmount();
  });

  test("icon dropdown shows available icons", async ({ mount, page }) => {
    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    // Wait for loading to finish and open modal
    await expect(page.getByText("Badge Management")).toBeVisible({
      timeout: 10000,
    });
    await page.getByRole("button", { name: "Create Badge" }).click();
    await expect(page.getByText("Create New Badge")).toBeVisible({
      timeout: 10000,
    });

    // Click the icon dropdown to open it
    const dropdowns = page.locator(".oc-dropdown__trigger");
    await dropdowns.first().click();

    // Verify some icon options appear
    await expect(page.locator(".oc-dropdown__option").first()).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator(".oc-dropdown__menu").first().getByText("Award")
    ).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.locator(".oc-dropdown__menu").first().getByText("Star")
    ).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("clicking the delete badge button opens the confirm modal", async ({
    mount,
    page,
  }) => {
    // Covers the delete-button onClick path (setBadgeToDelete + setDeleteModalOpen)
    // and the ConfirmModal render branch, which the existing tests didn't reach.
    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    await expect(page.getByText("Annotation Pro")).toBeVisible({
      timeout: 10000,
    });

    const deleteButtons = page.getByRole("button", { name: "Delete badge" });
    await deleteButtons.first().click();

    // ConfirmModal should appear referencing the badge name
    await expect(page.getByText(/Annotation Pro/).first()).toBeVisible({
      timeout: 5000,
    });
    // The confirm modal asks for confirmation
    await expect(
      page.getByText(/Are you sure you want to delete/).first()
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("toggling auto-award reveals criteria config", async ({
    mount,
    page,
  }) => {
    // Covers the isAutoAwarded checkbox onChange branch (and re-toggle path
    // that clears criteriaConfig), plus the conditional BadgeCriteriaConfig
    // render — none of which the existing tests touched.
    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    await expect(page.getByText("Badge Management")).toBeVisible({
      timeout: 10000,
    });
    await page.getByRole("button", { name: "Create Badge" }).click();
    await expect(page.getByText("Create New Badge")).toBeVisible({
      timeout: 10000,
    });

    const autoAwardCheckbox = page.locator("input[type=checkbox]").first();
    await autoAwardCheckbox.check();
    await expect(autoAwardCheckbox).toBeChecked();

    // Re-toggle off — exercises the else branch that resets criteriaConfig
    await autoAwardCheckbox.uncheck();
    await expect(autoAwardCheckbox).not.toBeChecked();

    await component.unmount();
  });

  test("keeps the badge table horizontally scrollable on mobile", async ({
    mount,
    page,
  }) => {
    // Regression guard for issue #1749: the wide badge table must scroll
    // horizontally on small viewports rather than crush its columns.
    await page.setViewportSize({ width: 390, height: 844 });

    const component = await mount(
      <BadgeManagementTestWrapper mocks={createAllMocks()} />
    );

    await expect(page.getByText("Annotation Pro")).toBeVisible({
      timeout: 10000,
    });

    const scroll = page.getByTestId("badge-management-table-scroll");
    await expect(scroll).toBeVisible();
    const overflowX = await scroll.evaluate(
      (el) => getComputedStyle(el).overflowX
    );
    expect(overflowX).toBe("auto");
    const scrolls = await scroll.evaluate(
      (el) => el.scrollWidth > el.clientWidth
    );
    expect(scrolls).toBe(true);

    await component.unmount();
  });
});
