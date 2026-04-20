/**
 * Additional Playwright Component Tests for LabelSetDetailPage
 *
 * Supplements LabelSetDetailPage.ct.tsx with coverage for the mutation success
 * paths and UI branches that the original file only renders (never submits).
 * Related to issue #1286 — coverage target ≥60%.
 *
 * Covers:
 * - Overview tab: export JSON, Delete-with-confirmation flow, permission-hidden delete button
 * - Inline edit form: fill + save mutation success path
 * - Create label mutation success path
 * - Delete label mutation success path
 * - Doc Labels & Relationships tabs
 * - Error state from failed query
 * - Sharing tab
 * - Empty-state "Add First Label" branch
 */

import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { LabelSetDetailPageTestWrapper } from "./LabelSetDetailPageTestWrapper";
import { GET_LABELSET_WITH_ALL_LABELS } from "../src/graphql/queries";
import {
  CREATE_ANNOTATION_LABEL_FOR_LABELSET,
  DELETE_LABELSET,
  DELETE_MULTIPLE_ANNOTATION_LABELS,
  UPDATE_ANNOTATION_LABEL,
} from "../src/graphql/mutations";
import { openedLabelset } from "../src/graphql/cache";

// ──────────────────────────────────────────────────────────────────────────────
// MOCK DATA
// ──────────────────────────────────────────────────────────────────────────────

const LABELSET_ID = "TGFiZWxTZXRUeXBlOjE=";

const baseLabelset = {
  __typename: "LabelSetType" as const,
  id: LABELSET_ID,
  icon: null,
  title: "Coverage Label Set",
  description: "Label set used by coverage tests.",
  created: "2024-01-15T10:00:00Z",
  modified: "2024-01-20T15:30:00Z",
  isPublic: false,
  docLabelCount: 1,
  spanLabelCount: 1,
  tokenLabelCount: 1,
  corpusCount: 0,
  creator: {
    __typename: "UserType" as const,
    id: "user-1",
    slug: "testuser",
    username: "testuser",
    email: "test@example.com",
  },
};

const spanLabel = {
  __typename: "AnnotationLabelType" as const,
  id: "label-span-1",
  icon: "tag",
  labelType: "SPAN_LABEL",
  readOnly: false,
  text: "Entity Name",
  description: "Identifies entity names",
  color: "cc0066",
  myPermissions: ["READ", "UPDATE", "DELETE"],
  isPublic: false,
  analyzer: null,
};

const docLabel = {
  __typename: "AnnotationLabelType" as const,
  id: "label-doc-1",
  icon: "file",
  labelType: "DOC_TYPE_LABEL",
  readOnly: false,
  text: "Contract",
  description: "Legal contract document",
  color: "00cc66",
  myPermissions: ["READ", "UPDATE", "DELETE"],
  isPublic: false,
  analyzer: null,
};

const relationshipLabel = {
  __typename: "AnnotationLabelType" as const,
  id: "label-rel-1",
  icon: "arrows alternate horizontal",
  labelType: "RELATIONSHIP_LABEL",
  readOnly: false,
  text: "References",
  description: "Document references another document",
  color: "0099cc",
  myPermissions: ["READ", "UPDATE", "DELETE"],
  isPublic: false,
  analyzer: null,
};

const textLabel = {
  __typename: "AnnotationLabelType" as const,
  id: "label-text-1",
  icon: "tag",
  labelType: "TOKEN_LABEL",
  readOnly: false,
  text: "Important",
  description: "Important text",
  color: "0066cc",
  myPermissions: ["READ", "UPDATE", "DELETE"],
  isPublic: false,
  analyzer: null,
};

const fullLabelset = {
  ...baseLabelset,
  myPermissions: ["read_labelset", "update_labelset", "remove_labelset"],
  allAnnotationLabels: [textLabel, docLabel, spanLabel, relationshipLabel],
};

const readOnlyLabelset = {
  ...baseLabelset,
  myPermissions: ["read_labelset"],
  allAnnotationLabels: [textLabel, docLabel, spanLabel, relationshipLabel],
};

// ──────────────────────────────────────────────────────────────────────────────
// MOCK FACTORIES
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Produce N copies of the labelset query mock. We avoid `maxUsageCount: Infinity`
 * because it prevents later state-change mocks with the same query+variables
 * from ever being used; Apollo's MockedProvider matches each request against
 * the first unused mock with matching variables.
 */
const labelsetQueryMocks = (labelset: any, count: number): MockedResponse[] =>
  Array.from({ length: count }, () => ({
    request: {
      query: GET_LABELSET_WITH_ALL_LABELS,
      variables: { id: labelset.id },
    },
    result: { data: { labelset } },
  }));

const updateLabelMock = (
  id: string,
  updates: { text?: string; description?: string; color?: string },
  success = true
): MockedResponse => ({
  request: {
    query: UPDATE_ANNOTATION_LABEL,
    variables: {
      id,
      text: updates.text,
      description: updates.description,
      color: updates.color,
    },
  },
  result: {
    data: {
      updateAnnotationLabel: {
        ok: success,
        message: success ? null : "Failed to update",
      },
    },
  },
});

const deleteLabelsMock = (ids: string[], success = true): MockedResponse => ({
  request: {
    query: DELETE_MULTIPLE_ANNOTATION_LABELS,
    variables: { annotationLabelIdsToDelete: ids },
  },
  result: {
    data: {
      deleteMultipleAnnotationLabels: {
        ok: success,
        message: success ? null : "Failed to delete",
      },
    },
  },
});

const createLabelMock = (
  labelsetId: string,
  label: {
    text: string;
    description: string;
    color: string;
    labelType: string;
  },
  success = true
): MockedResponse => ({
  request: {
    query: CREATE_ANNOTATION_LABEL_FOR_LABELSET,
    variables: {
      color: label.color,
      description: label.description,
      icon: "tag",
      text: label.text,
      labelType: label.labelType,
      labelsetId,
    },
  },
  result: {
    data: {
      createAnnotationLabelForLabelset: {
        ok: success,
        message: success ? null : "Failed to create",
      },
    },
  },
});

const deleteLabelsetMock = (id: string, success = true): MockedResponse => ({
  request: {
    query: DELETE_LABELSET,
    variables: { id },
  },
  result: {
    data: {
      deleteLabelset: {
        ok: success,
        message: success ? null : "Failed to delete labelset",
      },
    },
  },
});

// ──────────────────────────────────────────────────────────────────────────────
// HELPERS
// ──────────────────────────────────────────────────────────────────────────────

const mountPage = (
  mount: any,
  mocks: MockedResponse[],
  permissions: string[] = [
    "read_labelset",
    "update_labelset",
    "remove_labelset",
  ]
) => {
  openedLabelset({
    id: LABELSET_ID,
    myPermissions: permissions,
  } as any);

  return mount(
    <LabelSetDetailPageTestWrapper
      mocks={mocks}
      labelsetId={LABELSET_ID}
      permissions={permissions}
    />
  );
};

// ──────────────────────────────────────────────────────────────────────────────
// TESTS
// ──────────────────────────────────────────────────────────────────────────────

test.describe("LabelSetDetailPage – coverage", () => {
  test.describe("Overview tab", () => {
    test(
      "renders total-label stats and export button for editors",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        const component = await mountPage(mount, mocks);

        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });
        await expect(component.getByText("Total Labels")).toBeVisible();
        await expect(
          component.getByRole("button", { name: /Export JSON/i })
        ).toBeVisible();
      }
    );

    test(
      "shows Delete action and opens confirm modal",
      { timeout: 20000 },
      async ({ mount, page }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component
          .getByRole("button", { name: /^Delete$/i })
          .first()
          .click();

        // ConfirmModal is rendered via a portal, so query via `page`.
        await expect(
          page.getByText(/Are you sure you want to delete/i)
        ).toBeVisible({ timeout: 10000 });
      }
    );

    test(
      "hides Delete action for read-only viewers",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(readOnlyLabelset, 2);

        const component = await mountPage(mount, mocks, ["read_labelset"]);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await expect(
          component.getByRole("button", { name: /^Delete$/i })
        ).not.toBeVisible();
        await expect(
          component.getByRole("button", { name: /Export JSON/i })
        ).toBeVisible();
      }
    );

    test(
      "triggers export JSON click (covers handleExportJSON)",
      { timeout: 20000 },
      async ({ mount, page }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        // Stub out URL.createObjectURL so we exercise the handler without
        // triggering a real download in the sandbox.
        await page.addInitScript(() => {
          // @ts-ignore
          window.URL.createObjectURL = () => "blob:mock";
          // @ts-ignore
          window.URL.revokeObjectURL = () => undefined;
        });

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Export JSON/i }).click();

        // If we reach here without an uncaught exception, handleExportJSON ran.
        await expect(component.getByText("Coverage Label Set")).toBeVisible();
      }
    );

    test(
      "hides Edit Details footer button for viewers",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(readOnlyLabelset, 2);

        const component = await mountPage(mount, mocks, ["read_labelset"]);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await expect(
          component.getByRole("button", { name: /Edit Details/i })
        ).not.toBeVisible();
      }
    );
  });

  test.describe("Inline edit flow", () => {
    test(
      "saves edits via UPDATE_ANNOTATION_LABEL mutation",
      { timeout: 25000 },
      async ({ mount }) => {
        const updatedLabelset = {
          ...fullLabelset,
          allAnnotationLabels: fullLabelset.allAnnotationLabels.map((l) =>
            l.id === spanLabel.id ? { ...l, text: "Entity Name Updated" } : l
          ),
        };

        const mocks: MockedResponse[] = [
          ...labelsetQueryMocks(fullLabelset, 1),
          updateLabelMock(spanLabel.id, {
            text: "Entity Name Updated",
            description: spanLabel.description,
            color: spanLabel.color,
          }),
          ...labelsetQueryMocks(updatedLabelset, 2),
        ];

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Span Labels/i }).click();
        await expect(
          component.getByText("Entity Name", { exact: true })
        ).toBeVisible();

        // `force: true` skips the visibility (opacity) check; hover is a CSS
        // affordance, not a functional gate on clicks.
        await component.getByTitle("Edit").first().click({ force: true });

        const nameInput = component.getByPlaceholder("Label name");
        await expect(nameInput).toBeVisible({ timeout: 10000 });
        await nameInput.fill("Entity Name Updated");

        await component.getByTitle("Save").click();

        await expect(
          component.getByText("Entity Name Updated", { exact: true })
        ).toBeVisible({ timeout: 10000 });
      }
    );

    test(
      "cancels edit without mutation",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Span Labels/i }).click();
        await expect(
          component.getByText("Entity Name", { exact: true })
        ).toBeVisible();

        await component.getByTitle("Edit").first().click({ force: true });

        const nameInput = component.getByPlaceholder("Label name");
        await expect(nameInput).toBeVisible();

        await component.getByTitle("Cancel").click();

        await expect(nameInput).not.toBeVisible();
        await expect(
          component.getByText("Entity Name", { exact: true })
        ).toBeVisible();
      }
    );
  });

  test.describe("Create label flow", () => {
    test(
      "creates a new span label via CREATE_ANNOTATION_LABEL_FOR_LABELSET",
      { timeout: 25000 },
      async ({ mount }) => {
        const newLabel = {
          __typename: "AnnotationLabelType" as const,
          id: "label-span-new",
          icon: "tag",
          labelType: "SPAN_LABEL",
          readOnly: false,
          text: "Brand New Span",
          description: "",
          color: "0F766E",
          myPermissions: ["READ", "UPDATE", "DELETE"],
          isPublic: false,
          analyzer: null,
        };

        const labelsetAfterCreate = {
          ...fullLabelset,
          spanLabelCount: 2,
          allAnnotationLabels: [...fullLabelset.allAnnotationLabels, newLabel],
        };

        const mocks: MockedResponse[] = [
          ...labelsetQueryMocks(fullLabelset, 1),
          createLabelMock(LABELSET_ID, {
            text: "Brand New Span",
            description: "",
            color: "0F766E",
            labelType: "SPAN_LABEL",
          }),
          ...labelsetQueryMocks(labelsetAfterCreate, 2),
        ];

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Span Labels/i }).click();
        await expect(
          component.getByText("Entity Name", { exact: true })
        ).toBeVisible();

        await component.getByRole("button", { name: /Add Label/i }).click();

        const nameInput = component.getByPlaceholder("Enter label name");
        await expect(nameInput).toBeVisible();
        await nameInput.fill("Brand New Span");

        await component.getByTitle("Create").click();

        await expect(
          component.getByText("Brand New Span", { exact: true })
        ).toBeVisible({ timeout: 10000 });
      }
    );
  });

  test.describe("Delete label flow", () => {
    test(
      "deletes a span label via DELETE_MULTIPLE_ANNOTATION_LABELS",
      { timeout: 25000 },
      async ({ mount }) => {
        const labelsetAfterDelete = {
          ...fullLabelset,
          spanLabelCount: 0,
          allAnnotationLabels: fullLabelset.allAnnotationLabels.filter(
            (l) => l.id !== spanLabel.id
          ),
        };

        const mocks: MockedResponse[] = [
          ...labelsetQueryMocks(fullLabelset, 1),
          deleteLabelsMock([spanLabel.id]),
          ...labelsetQueryMocks(labelsetAfterDelete, 2),
        ];

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Span Labels/i }).click();
        await expect(
          component.getByText("Entity Name", { exact: true })
        ).toBeVisible();

        await component.getByTitle("Delete").first().click({ force: true });

        // After refetch, the span label is gone and the empty-state appears.
        await expect(component.getByText(/No span labels yet/i)).toBeVisible({
          timeout: 15000,
        });
      }
    );
  });

  test.describe("Delete labelset flow", () => {
    test(
      "deletes the labelset after confirming",
      { timeout: 25000 },
      async ({ mount, page }) => {
        const mocks: MockedResponse[] = [
          ...labelsetQueryMocks(fullLabelset, 2),
          deleteLabelsetMock(LABELSET_ID),
        ];

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component
          .getByRole("button", { name: /^Delete$/i })
          .first()
          .click();

        // Confirm modal is rendered via a portal on document.body.
        await expect(
          page.getByText(/Are you sure you want to delete/i)
        ).toBeVisible({ timeout: 10000 });

        await page.getByRole("button", { name: /^Yes$/ }).click();

        // Success triggers navigate("/label_sets"); the modal should close.
        await expect(
          page.getByText(/Are you sure you want to delete/i)
        ).not.toBeVisible({ timeout: 10000 });
      }
    );
  });

  test.describe("Tab navigation & misc views", () => {
    test(
      "Doc Labels tab shows search with no-match message",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Doc Labels/i }).click();
        await expect(
          component.getByText("Contract", { exact: true })
        ).toBeVisible();

        const search = component.getByPlaceholder(/Search doc labels/i);
        await search.fill("definitely-not-present");
        await expect(
          component.getByText(/No labels match "definitely-not-present"/i)
        ).toBeVisible();
      }
    );

    test(
      "Relationships tab renders relationship labels",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Relationships/i }).click();
        await expect(
          component.getByText("References", { exact: true })
        ).toBeVisible();
      }
    );

    test(
      "Sharing tab renders the placeholder panel",
      { timeout: 20000 },
      async ({ mount }) => {
        const mocks = labelsetQueryMocks(fullLabelset, 2);

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component
          .getByRole("button", { name: /^Sharing$/ })
          .first()
          .click();
        await expect(component.getByText("Sharing Settings")).toBeVisible();
      }
    );

    test(
      "renders error state when the query errors out",
      { timeout: 20000 },
      async ({ mount }) => {
        const erroringMock: MockedResponse = {
          request: {
            query: GET_LABELSET_WITH_ALL_LABELS,
            variables: { id: LABELSET_ID },
          },
          error: new Error("boom"),
        };

        const component = await mountPage(mount, [erroringMock]);

        await expect(
          component.getByText(/Error loading label set/i)
        ).toBeVisible({ timeout: 10000 });
      }
    );
  });

  test.describe("Empty-state create path", () => {
    test(
      "Add First Label opens the inline create form in the empty state",
      { timeout: 20000 },
      async ({ mount }) => {
        const emptySpanLabelset = {
          ...fullLabelset,
          spanLabelCount: 0,
          allAnnotationLabels: fullLabelset.allAnnotationLabels.filter(
            (l) => l.labelType !== "SPAN_LABEL"
          ),
        };

        const mocks = labelsetQueryMocks(emptySpanLabelset, 2);

        const component = await mountPage(mount, mocks);
        await expect(component.getByText("Coverage Label Set")).toBeVisible({
          timeout: 10000,
        });

        await component.getByRole("button", { name: /Span Labels/i }).click();
        await expect(component.getByText(/No span labels yet/i)).toBeVisible();

        await component
          .getByRole("button", { name: /Add First Label/i })
          .click();

        await expect(
          component.getByPlaceholder("Enter label name")
        ).toBeVisible();
      }
    );
  });
});
