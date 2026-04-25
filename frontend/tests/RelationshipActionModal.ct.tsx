import { test, expect } from "./utils/coverage";
// IMPORTANT: Keep JSX-component imports on their own line per the Playwright
// CT split-import rule (CLAUDE.md pitfall #16). Helpers live in a separate
// plain `.ts` fixtures file so the transform safely rewrites wrapper refs.
import { RelationshipActionModalTestWrapper } from "./RelationshipActionModalTestWrapper";
import { buildRelationLabel } from "./RelationshipActionModalFixtures";
import { docScreenshot } from "./utils/docScreenshot";
import { RelationGroup } from "../src/components/annotator/types/annotations";
import { SMART_LABEL_SEARCH_OR_CREATE } from "../src/graphql/mutations";
import { LabelType } from "../src/types/graphql-api";

const TIMEOUT = 10000;

test.describe("RelationshipActionModal", () => {
  test("renders modal with selected annotations", async ({ mount, page }) => {
    const component = await mount(<RelationshipActionModalTestWrapper />);

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    // Verify selected annotation count is displayed
    await expect(page.getByText("Selected: 2 annotations")).toBeVisible({
      timeout: TIMEOUT,
    });

    // Verify the two mode radio buttons are present
    await expect(page.getByText("Add to existing relationship")).toBeVisible({
      timeout: TIMEOUT,
    });
    await expect(page.getByText("Create new relationship")).toBeVisible({
      timeout: TIMEOUT,
    });

    // Verify footer buttons
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible({
      timeout: TIMEOUT,
    });

    // Without a corpus loaded in Jotai, the "No Corpus Selected" error should show
    await expect(page.getByText("No Corpus Selected")).toBeVisible({
      timeout: TIMEOUT,
    });

    await docScreenshot(
      page,
      "knowledge-base--relationship-action-modal--initial"
    );

    await component.unmount();
  });

  test("create mode radio is disabled without corpus state", async ({
    mount,
    page,
  }) => {
    const component = await mount(<RelationshipActionModalTestWrapper />);

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    // Without corpus state, the "Create new relationship" radio should be disabled
    const createRadio = page.locator('input[type="radio"][value="create"]');
    await expect(createRadio).toBeDisabled();

    // The "Add to existing" radio should be checked by default
    const addRadio = page.locator('input[type="radio"][value="add"]');
    await expect(addRadio).toBeChecked();

    await docScreenshot(
      page,
      "knowledge-base--relationship-action-modal--create-disabled"
    );

    await component.unmount();
  });

  test("shows no editable relationships message in add mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <RelationshipActionModalTestWrapper existingRelationships={[]} />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    // In add mode with no existing relationships, empty message shows
    await expect(page.getByText("No editable relationships found")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await component.unmount();
  });
});

/* -------------------------------------------------------------------------- */
/* Modal with corpus state - drives fuller flows                              */
/* -------------------------------------------------------------------------- */

test.describe("RelationshipActionModal - with corpus loaded", () => {
  test("hides 'No Corpus Selected' error when corpus is loaded", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <RelationshipActionModalTestWrapper withCorpus={true} hasLabelset />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );
    await expect(page.getByText("No Corpus Selected")).not.toBeVisible();

    // Both radios are enabled
    await expect(
      page.locator('input[type="radio"][value="add"]')
    ).toBeEnabled();
    await expect(
      page.locator('input[type="radio"][value="create"]')
    ).toBeEnabled();

    await component.unmount();
  });

  test("selecting existing relationship enables role picker and submit", async ({
    mount,
    page,
  }) => {
    const rel = new RelationGroup(
      ["ann-src"],
      ["ann-tgt"],
      buildRelationLabel("rel-label-1", "Cites"),
      "rel-1",
      false
    );

    let addArgs: { id: string; role: "source" | "target" } | null = null;
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        existingRelationships={[rel]}
        relationLabels={[buildRelationLabel("rel-label-1", "Cites")]}
        onAddToExisting={async (id, role) => {
          addArgs = { id, role };
        }}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    // Empty message should NOT be shown
    await expect(
      page.getByText("No editable relationships found")
    ).not.toBeVisible();

    // The relationship option should be clickable
    await page.getByText("Cites").first().click();

    // Role picker appears
    await expect(page.getByText("Add selected annotations as:")).toBeVisible();
    await expect(page.getByText("Source annotations")).toBeVisible();
    await expect(page.getByText("Target annotations")).toBeVisible();

    // Submit button should now be "Add to Relationship" and enabled
    const submit = page.getByRole("button", { name: "Add to Relationship" });
    await expect(submit).toBeEnabled();

    // Flip role to target
    await page.locator('input[type="radio"][value="target"]').check();

    await submit.click();

    await expect
      .poll(() => addArgs, { timeout: TIMEOUT })
      .toEqual({ id: "rel-1", role: "target" });

    await component.unmount();
  });

  test("structural relationships are filtered out", async ({ mount, page }) => {
    const editable = new RelationGroup(
      ["ann-1"],
      ["ann-2"],
      buildRelationLabel("rel-label-1", "Cites"),
      "rel-1",
      false
    );
    const structural = new RelationGroup(
      ["ann-3"],
      ["ann-4"],
      buildRelationLabel("rel-label-2", "StructuralOnly"),
      "rel-2",
      true
    );

    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        existingRelationships={[editable, structural]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await expect(page.getByText("Cites")).toBeVisible();
    await expect(page.getByText("StructuralOnly")).not.toBeVisible();

    await component.unmount();
  });

  test("switching to create mode shows label search", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={[
          buildRelationLabel("rel-label-1", "References"),
          buildRelationLabel("rel-label-2", "Cites"),
        ]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    // Switch to create mode
    await page.locator('input[type="radio"][value="create"]').check();

    await expect(
      page.getByText("Search or Create Relationship Label")
    ).toBeVisible();
    await expect(
      page.getByPlaceholder("Search for a relationship label...")
    ).toBeVisible();

    // Submit is disabled until a label and at least one assignment are selected
    const submit = page.getByRole("button", { name: "Create Relationship" });
    await expect(submit).toBeDisabled();

    await component.unmount();
  });

  test("warning shows when corpus lacks a labelset in create mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset={false}
        relationLabels={[]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();

    await expect(page.getByText("No labelset found.")).toBeVisible();

    await component.unmount();
  });

  test("label search filters the dropdown options", async ({ mount, page }) => {
    const labels = [
      buildRelationLabel("rel-a", "References"),
      buildRelationLabel("rel-b", "Cites"),
      buildRelationLabel("rel-c", "Defines"),
    ];
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={labels}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();

    const searchInput = page.getByPlaceholder(
      "Search for a relationship label..."
    );
    await searchInput.fill("Cit");

    // Only "Cites" should be matched
    await expect(page.getByText("No matching labels found.")).not.toBeVisible();

    // Searching gibberish produces "No matching labels"
    await searchInput.fill("zzzzzz");
    await expect(page.getByText("No matching labels found.")).toBeVisible();

    // A "Create" affordance is offered when there's a search term
    await expect(
      page.getByRole("button", { name: /Create "zzzzzz" label/ })
    ).toBeVisible();

    await component.unmount();
  });

  test("create label form toggles open and cancels back to search", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={[]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();

    const searchInput = page.getByPlaceholder(
      "Search for a relationship label..."
    );
    await searchInput.fill("NewRel");

    await page.getByRole("button", { name: /Create "NewRel" label/ }).click();

    // Form fields show
    await expect(page.getByPlaceholder("Enter label name")).toBeVisible();
    await expect(page.getByPlaceholder("Enter description")).toBeVisible();
    await expect(page.locator('input[type="color"]')).toBeVisible();

    // Cancel returns to search UI
    await page.getByRole("button", { name: "Cancel" }).first().click();
    await expect(page.getByPlaceholder("Enter label name")).not.toBeVisible();
    await expect(searchInput).toBeVisible();

    await component.unmount();
  });

  test("creating label via smart-label mutation selects it afterward", async ({
    mount,
    page,
  }) => {
    // The modal's default color is OS_LEGAL_COLORS.greenMedium = "#10b981"
    const createMock = {
      request: {
        query: SMART_LABEL_SEARCH_OR_CREATE,
        variables: {
          corpusId: "corpus-1",
          searchTerm: "BrandNewRel",
          labelType: LabelType.RelationshipLabel,
          color: "#10b981",
          description: "",
          createIfNotFound: true,
        },
      },
      result: {
        data: {
          smartLabelSearchOrCreate: {
            ok: true,
            message: "Created",
            labels: [
              {
                id: "created-label-1",
                text: "BrandNewRel",
                description: "",
                color: "#10b981",
                icon: null,
                labelType: LabelType.RelationshipLabel,
              },
            ],
            labelset: null,
            labelsetCreated: false,
            labelCreated: true,
          },
        },
      },
    };

    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={[]}
        mocks={[createMock]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();
    await page
      .getByPlaceholder("Search for a relationship label...")
      .fill("BrandNewRel");
    await page
      .getByRole("button", { name: /Create "BrandNewRel" label/ })
      .click();

    await page.getByRole("button", { name: "Create Label" }).click();

    // After creation, the "Selected Label" block appears with the new label
    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: TIMEOUT,
    });
    await expect(page.getByText("BrandNewRel").first()).toBeVisible();

    // A "Change" button lets you clear the selected label and return to search
    await page.getByRole("button", { name: "Change" }).click();
    await expect(page.getByText("Selected Label")).not.toBeVisible();
    await expect(
      page.getByPlaceholder("Search for a relationship label...")
    ).toBeVisible();

    await component.unmount();
  });

  test("create mode: submit disabled until label and assignments set", async ({
    mount,
    page,
  }) => {
    const labels = [buildRelationLabel("rel-a", "References")];
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={labels}
        selectedAnnotationIds={["a1", "a2"]}
        annotations={[
          { id: "a1", rawText: "First text with details" },
          { id: "a2", rawText: "Short" },
        ]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();

    const submit = page.getByRole("button", { name: "Create Relationship" });
    await expect(submit).toBeDisabled();

    await component.unmount();
  });

  test("submitting creates relationship with assigned source/target", async ({
    mount,
    page,
  }) => {
    const labels = [buildRelationLabel("rel-a", "References")];
    let createArgs: {
      labelId: string;
      sourceIds: string[];
      targetIds: string[];
    } | null = null;

    const searchMock = {
      request: {
        query: SMART_LABEL_SEARCH_OR_CREATE,
        variables: {
          corpusId: "corpus-1",
          searchTerm: "References",
          labelType: LabelType.RelationshipLabel,
          color: "#10b981",
          description: "",
          createIfNotFound: true,
        },
      },
      result: {
        data: {
          smartLabelSearchOrCreate: {
            ok: true,
            message: "Selected",
            labels: [
              {
                id: "rel-a",
                text: "References",
                description: "",
                color: "#10b981",
                icon: null,
                labelType: LabelType.RelationshipLabel,
              },
            ],
            labelset: null,
            labelsetCreated: false,
            labelCreated: false,
          },
        },
      },
    };

    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={labels}
        selectedAnnotationIds={["a1", "a2"]}
        annotations={[
          { id: "a1", rawText: "AlphaFirstPill" },
          { id: "a2", rawText: "BetaSecondPill" },
        ]}
        mocks={[searchMock]}
        onCreate={async (labelId, sourceIds, targetIds) => {
          createArgs = { labelId, sourceIds, targetIds };
        }}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();

    await page
      .getByPlaceholder("Search for a relationship label...")
      .fill("References");

    // Invoke the "Create 'References' label" path which selects the existing
    // label via the smart search mutation mock.
    await page
      .getByRole("button", { name: /Create "References" label/ })
      .click();

    await page.getByRole("button", { name: "Create Label" }).click();

    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: TIMEOUT,
    });

    // Each annotation is rendered once in the Source section and once in the
    // Target section. nth(0) is inside Source Annotations, nth(1) is inside
    // Target Annotations.
    await page.locator("text=AlphaFirstPill").nth(0).click(); // a1 → source
    await page.locator("text=BetaSecondPill").nth(1).click(); // a2 → target

    const submit = page.getByRole("button", { name: "Create Relationship" });
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect
      .poll(() => createArgs, { timeout: TIMEOUT })
      .toEqual({
        labelId: "rel-a",
        sourceIds: ["a1"],
        targetIds: ["a2"],
      });

    await component.unmount();
  });

  test("cancel button invokes onClose", async ({ mount, page }) => {
    let closed = false;
    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        onClose={() => {
          closed = true;
        }}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.getByRole("button", { name: "Cancel" }).click();

    await expect.poll(() => closed, { timeout: TIMEOUT }).toBe(true);

    await component.unmount();
  });

  test("annotation preview truncates long text with ellipsis", async ({
    mount,
    page,
  }) => {
    const longText =
      "This is a very long annotation text that should definitely exceed thirty characters";
    const labels = [buildRelationLabel("rel-a", "References")];

    const searchMock = {
      request: {
        query: SMART_LABEL_SEARCH_OR_CREATE,
        variables: {
          corpusId: "corpus-1",
          searchTerm: "References",
          labelType: LabelType.RelationshipLabel,
          color: "#10b981",
          description: "",
          createIfNotFound: true,
        },
      },
      result: {
        data: {
          smartLabelSearchOrCreate: {
            ok: true,
            message: "ok",
            labels: [
              {
                id: "rel-a",
                text: "References",
                description: "",
                color: "#10b981",
                icon: null,
                labelType: LabelType.RelationshipLabel,
              },
            ],
            labelset: null,
            labelsetCreated: false,
            labelCreated: false,
          },
        },
      },
    };

    const component = await mount(
      <RelationshipActionModalTestWrapper
        withCorpus
        hasLabelset
        relationLabels={labels}
        selectedAnnotationIds={["ann-long"]}
        annotations={[{ id: "ann-long", rawText: longText }]}
        mocks={[searchMock]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    await page.locator('input[type="radio"][value="create"]').check();
    await page
      .getByPlaceholder("Search for a relationship label...")
      .fill("References");
    await page
      .getByRole("button", { name: /Create "References" label/ })
      .click();
    await page.getByRole("button", { name: "Create Label" }).click();

    await expect(page.getByText("Selected Label")).toBeVisible({
      timeout: TIMEOUT,
    });

    // Ellipsis text is visible
    await expect(page.getByText(/…|\.\.\./).first()).toBeVisible();

    await component.unmount();
  });

  test("single selected annotation renders 'annotation' (not plural)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <RelationshipActionModalTestWrapper
        selectedAnnotationIds={["only-1"]}
        annotations={[{ id: "only-1", rawText: "Lonely one" }]}
      />
    );

    await expect(page.getByText("Add Annotations to Relationship")).toBeVisible(
      { timeout: TIMEOUT }
    );

    const infoBoxText = await page
      .locator("strong")
      .filter({ hasText: "Selected:" })
      .textContent();
    expect(infoBoxText?.replace(/\s+/g, " ").trim()).toBe(
      "Selected: 1 annotation"
    );

    await component.unmount();
  });
});
