import { test, expect } from "@playwright/experimental-ct-react";
import { FloatingDocumentControlsTestWrapper } from "./FloatingDocumentControlsTestWrapper";

test.describe("FloatingDocumentControls", () => {
  test("renders visible controls with all buttons", async ({ mount, page }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        corpusPermissions={["CAN_READ", "CAN_UPDATE"]}
      />
    );

    // Check main container is visible
    await expect(component).toBeVisible();

    // Check all buttons are present
    const settingsButton = component
      .getByRole("button")
      .filter({ has: page.locator("svg") })
      .first();
    await expect(settingsButton).toBeVisible();

    const extractsButton = component
      .getByRole("button")
      .filter({ has: page.locator("svg") })
      .nth(1);
    await expect(extractsButton).toBeVisible();
    await expect(extractsButton).toHaveAttribute("title", "View Extracts");

    const analysesButton = component
      .getByRole("button")
      .filter({ has: page.locator("svg") })
      .nth(2);
    await expect(analysesButton).toBeVisible();
    await expect(analysesButton).toHaveAttribute("title", "View Analyses");

    const createAnalysisButton = component
      .getByRole("button")
      .filter({ has: page.locator("svg") })
      .nth(3);
    await expect(createAnalysisButton).toBeVisible();
    await expect(createAnalysisButton).toHaveAttribute(
      "title",
      "Start New Analysis"
    );
  });

  test("hides when visible prop is false", async ({ mount, page }) => {
    await mount(<FloatingDocumentControlsTestWrapper visible={false} />);

    // When visible is false, the component returns null, so no buttons should exist
    const buttons = await page.locator("button").all();
    expect(buttons.length).toBe(0);
  });

  test("expands settings panel when settings button is clicked", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper visible={true} />
    );

    const settingsButton = component.getByRole("button").first();
    await settingsButton.click();

    // Check the settings panel appears
    const settingsPanel = page.locator("text=Visualization Settings");
    await expect(settingsPanel).toBeVisible();

    // Check all toggle options are present
    await expect(page.locator("text=Show Only Selected")).toBeVisible();
    await expect(page.locator("text=Show Bounding Boxes")).toBeVisible();
    await expect(page.locator("text=Show Structural")).toBeVisible();
  });

  test("collapses settings panel when clicked again", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper visible={true} />
    );

    const settingsButton = component.getByRole("button").first();

    // Open panel
    await settingsButton.click();
    await expect(page.locator("text=Visualization Settings")).toBeVisible();

    // Close panel
    await settingsButton.click();
    await expect(page.locator("text=Visualization Settings")).not.toBeVisible();
  });

  test("calls onAnalysesClick when analyses button is clicked", async ({
    mount,
  }) => {
    let analysesCalled = false;
    const onAnalysesClick = () => {
      analysesCalled = true;
    };
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        onAnalysesClick={onAnalysesClick}
      />
    );

    const analysesButton = component.getByRole("button").nth(2);
    await analysesButton.click();

    expect(analysesCalled).toBe(true);
  });

  test("calls onExtractsClick when extracts button is clicked", async ({
    mount,
  }) => {
    let extractsCalled = false;
    const onExtractsClick = () => {
      extractsCalled = true;
    };
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        onExtractsClick={onExtractsClick}
      />
    );

    const extractsButton = component.getByRole("button").nth(1);
    await extractsButton.click();

    expect(extractsCalled).toBe(true);
  });

  test("closes extracts panel when analyses button is clicked if extracts panel is open", async ({
    mount,
  }) => {
    let analysesCalled = 0;
    let extractsCalled = 0;
    const onAnalysesClick = () => {
      analysesCalled++;
    };
    const onExtractsClick = () => {
      extractsCalled++;
    };

    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        onAnalysesClick={onAnalysesClick}
        onExtractsClick={onExtractsClick}
        extractsOpen={true}
        analysesOpen={false}
      />
    );

    const analysesButton = component.getByRole("button").nth(2);
    await analysesButton.click();

    // Should close extracts panel first
    expect(extractsCalled).toBe(1);
    // Then open analyses panel
    expect(analysesCalled).toBe(1);
  });

  test("closes analyses panel when extracts button is clicked if analyses panel is open", async ({
    mount,
  }) => {
    let analysesCalled = 0;
    let extractsCalled = 0;
    const onAnalysesClick = () => {
      analysesCalled++;
    };
    const onExtractsClick = () => {
      extractsCalled++;
    };

    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        onAnalysesClick={onAnalysesClick}
        onExtractsClick={onExtractsClick}
        analysesOpen={true}
        extractsOpen={false}
      />
    );

    const extractsButton = component.getByRole("button").nth(1);
    await extractsButton.click();

    // Should close analyses panel first
    expect(analysesCalled).toBe(1);
    // Then open extracts panel
    expect(extractsCalled).toBe(1);
  });

  test("hides create analysis button when user lacks permissions", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        corpusPermissions={["CAN_READ"]} // No CAN_UPDATE permission
      />
    );

    // Count only the floating action buttons (not settings panel buttons)
    const settingsButton = page.locator("button").first();
    const extractsButton = page.locator('button[title="View Extracts"]');
    const analysesButton = page.locator('button[title="View Analyses"]');

    await expect(settingsButton).toBeVisible();
    await expect(extractsButton).toBeVisible();
    await expect(analysesButton).toBeVisible();

    // The create analysis button should not be present
    const createAnalysisButton = page.locator(
      'button[title="Start New Analysis"]'
    );
    await expect(createAnalysisButton).not.toBeVisible();
  });

  test("toggles show selected only checkbox", async ({ mount, page }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        showSelectedOnly={false}
      />
    );

    // Open settings panel
    const settingsButton = component.getByRole("button").first();
    await settingsButton.click();

    // Find and click the toggle
    const toggleRow = page.locator("text=Show Only Selected").locator("..");
    const toggle = toggleRow.locator('input[type="checkbox"]');

    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await expect(toggle).toBeChecked();
  });

  test("toggles show bounding boxes checkbox", async ({ mount, page }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        showBoundingBoxes={false}
      />
    );

    // Open settings panel
    const settingsButton = component.getByRole("button").first();
    await settingsButton.click();

    // Find and click the toggle
    const toggleRow = page.locator("text=Show Bounding Boxes").locator("..");
    const toggle = toggleRow.locator('input[type="checkbox"]');

    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await expect(toggle).toBeChecked();
  });

  test("enabling structural view forces show selected only to be true", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        showSelectedOnly={false}
        showStructural={false}
      />
    );

    // Open settings panel
    const settingsButton = component.getByRole("button").first();
    await settingsButton.click();

    // Both should be initially unchecked
    const selectedOnlyToggle = page
      .locator("text=Show Only Selected")
      .locator("..")
      .locator('input[type="checkbox"]');
    const structuralToggle = page
      .locator("text=Show Structural")
      .locator("..")
      .locator('input[type="checkbox"]');

    await expect(selectedOnlyToggle).not.toBeChecked();
    await expect(structuralToggle).not.toBeChecked();

    // Click structural toggle
    await structuralToggle.click();

    // Both should now be checked
    await expect(structuralToggle).toBeChecked();
    await expect(selectedOnlyToggle).toBeChecked();

    // Selected only should be disabled when structural is on
    await expect(selectedOnlyToggle).toBeDisabled();
  });

  test("adjusts position based on panelOffset", async ({ mount }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper visible={true} panelOffset={400} />
    );

    // Check that the container has the correct right offset
    const container = component.locator("div").first();
    const styles = await container.evaluate((el) =>
      window.getComputedStyle(el)
    );

    // The right offset should be panelOffset + 32px = 432px
    expect(styles.right).toBe("432px");
  });

  test("shows create analysis button when user has permissions", async ({
    mount,
    page,
  }) => {
    await page.route("**/graphql", (route) => {
      // Mock any GraphQL requests if needed
      route.fulfill({ status: 200, body: JSON.stringify({ data: {} }) });
    });

    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        corpusPermissions={["CAN_READ", "CAN_UPDATE"]}
      />
    );

    // Check all 4 buttons are visible
    const settingsButton = page.locator("button").first();
    const extractsButton = page.locator('button[title="View Extracts"]');
    const analysesButton = page.locator('button[title="View Analyses"]');
    const createAnalysisButton = page.locator(
      'button[title="Start New Analysis"]'
    );

    await expect(settingsButton).toBeVisible();
    await expect(extractsButton).toBeVisible();
    await expect(analysesButton).toBeVisible();

    // The create analysis button should be present (already defined above)
    await expect(createAnalysisButton).toBeVisible();

    // Clicking it should trigger the modal (we can't test the actual modal behavior)
    await createAnalysisButton.click();
    // No error should occur
  });

  test("read-only: hides create analysis button even with permissions", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        readOnly={true}
        corpusPermissions={["CAN_READ", "CAN_UPDATE"]} // Has permissions
      />
    );

    // Count visible buttons
    const settingsButton = page.locator("button").first();
    const extractsButton = page.locator('button[title="View Extracts"]');
    const analysesButton = page.locator('button[title="View Analyses"]');

    await expect(settingsButton).toBeVisible();
    await expect(extractsButton).toBeVisible();
    await expect(analysesButton).toBeVisible();

    // The create analysis button should NOT be visible in read-only mode
    const createAnalysisButton = page.locator(
      'button[title="Start New Analysis"]'
    );
    await expect(createAnalysisButton).not.toBeVisible();
  });

  test("read-only: settings panel still functions normally", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        readOnly={true}
        showBoundingBoxes={false}
      />
    );

    // Open settings panel
    const settingsButton = component.getByRole("button").first();
    await settingsButton.click();

    // Settings panel should still be functional
    await expect(page.locator("text=Visualization Settings")).toBeVisible();

    // Toggle should still work
    const toggleRow = page.locator("text=Show Bounding Boxes").locator("..");
    const toggle = toggleRow.locator('input[type="checkbox"]');

    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await expect(toggle).toBeChecked();
  });

  test("read-only: view buttons remain functional", async ({ mount }) => {
    let analysesCalled = false;
    let extractsCalled = false;

    const component = await mount(
      <FloatingDocumentControlsTestWrapper
        visible={true}
        readOnly={true}
        onAnalysesClick={() => {
          analysesCalled = true;
        }}
        onExtractsClick={() => {
          extractsCalled = true;
        }}
      />
    );

    // View buttons should still work in read-only mode
    const extractsButton = component.getByRole("button").nth(1);
    await extractsButton.click();
    expect(extractsCalled).toBe(true);

    const analysesButton = component.getByRole("button").nth(2);
    await analysesButton.click();
    expect(analysesCalled).toBe(true);
  });
});
