import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusGroupManagementTestWrapper } from "./CorpusGroupManagementTestWrapper";
import {
  CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT,
  GET_MY_CORPUS_GROUPS,
  CREATE_CORPUS_GROUP,
  UPDATE_CORPUS_GROUP,
  DELETE_CORPUS_GROUP,
} from "../src/components/corpus_groups/graphql";
import { docScreenshot } from "./utils/docScreenshot";

/**
 * Imported, never re-declared. The panel sends this as the ``$corporaLimit``
 * variable on every list query AND on both mutations, so a local copy that
 * drifted from the real constant would make every mock silently fail to
 * match — and a value above the server's relay page cap would pass these
 * mocked tests while failing against the real schema.
 */
const MEMBERSHIP_FETCH_LIMIT = CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT;

/** Every id below is a relay global id — the mutations decode them server-side. */
const GROUP_ID = "Q29ycHVzR3JvdXBUeXBlOjM=";
const CORPUS_ID_MSA = "Q29ycHVzVHlwZTox";
const CORPUS_ID_NDA = "Q29ycHVzVHlwZToz";
const AGENT_ID = "QWdlbnRDb25maWc6NQ==";

const LIST_VARIABLES = {
  mine: true,
  corporaLimit: MEMBERSHIP_FETCH_LIMIT,
};

/* -------------------------------------------------------------------------- */
/* Fixtures                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * The pre-existing group used by the list/edit/delete tests.
 *
 * ``corpora.totalCount`` MUST equal ``corpora.edges.length``: the edit branch
 * of ``handleSubmit`` refuses to submit a truncated membership set (it would
 * silently drop the unloaded members, since ``updateCorpusGroup`` REPLACES
 * membership). A fixture where they disagree makes the edit test fail with no
 * mutation ever leaving the component.
 */
const vendorGroup = {
  id: GROUP_ID,
  title: "Vendor Agreements",
  slug: "vendor-agreements",
  description: "Master services and vendor contracts.",
  isPublic: true,
  created: "2026-07-01T12:00:00+00:00",
  modified: "2026-07-02T12:00:00+00:00",
  myPermissions: [
    "read_corpusgroup",
    "update_corpusgroup",
    "remove_corpusgroup",
  ],
  creator: { id: "user-1", displayName: "member" },
  defaultAgent: { id: AGENT_ID, name: "Contract Analyst" },
  corpora: {
    totalCount: 2,
    edges: [
      { node: { id: CORPUS_ID_MSA, title: "Master Service Agreements" } },
      { node: { id: CORPUS_ID_NDA, title: "Mutual NDAs" } },
    ],
  },
};

const litigationGroup = {
  id: "Q29ycHVzR3JvdXBUeXBlOjc=",
  title: "Litigation Bundle",
  slug: "litigation-bundle",
  description: "",
  isPublic: false,
  created: "2026-07-19T12:00:00+00:00",
  modified: "2026-07-19T12:00:00+00:00",
  myPermissions: [
    "read_corpusgroup",
    "update_corpusgroup",
    "remove_corpusgroup",
  ],
  creator: { id: "user-1", displayName: "member" },
  defaultAgent: null,
  corpora: { totalCount: 0, edges: [] },
};

const renamedVendorGroup = {
  ...vendorGroup,
  title: "Vendor Agreements 2026",
};

/* -------------------------------------------------------------------------- */
/* Mock builders                                                               */
/* -------------------------------------------------------------------------- */

/**
 * The list query is fired once on mount (``cache-and-network`` over an empty
 * cache) and once more per ``refetch()``. MockLink serves identically-keyed
 * mocks in array order, so a mutation test supplies ``[listBefore, mutation,
 * listAfter]`` and the refetch picks up the post-mutation state.
 */
const buildListMock = (groups: unknown[]): MockedResponse => ({
  request: { query: GET_MY_CORPUS_GROUPS, variables: LIST_VARIABLES },
  result: {
    data: {
      corpusGroups: {
        totalCount: groups.length,
        edges: groups.map((node) => ({ node })),
      },
    },
  },
});

test.describe("CorpusGroupManagement", () => {
  test("renders the empty state when the user has no groups", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper mocks={[buildListMock([])]} />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("No corpus groups yet")).toBeVisible({
      timeout: 20000,
    });
    // The empty state carries its own call to action alongside the header one.
    await expect(
      page.getByRole("button", { name: "Create your first group" })
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("new-corpus-group-button")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-groups-table")).toHaveCount(0);

    await docScreenshot(page, "corpus-groups--management-panel--empty");
  });

  test("lists existing groups and creates a new one", async ({
    mount,
    page,
  }) => {
    const createMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_GROUP,
        // Verbatim from the create branch of ``handleSubmit``: description,
        // corpusIds and isPublic are always sent (empty/false defaults
        // included); slug and defaultAgentId are OMITTED entirely when blank,
        // never sent as "" or null.
        variables: {
          title: "Litigation Bundle",
          description: "",
          corpusIds: [],
          isPublic: false,
          corporaLimit: MEMBERSHIP_FETCH_LIMIT,
        },
      },
      result: {
        data: {
          createCorpusGroup: {
            ok: true,
            message: "Created",
            corpusGroup: litigationGroup,
          },
        },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[
          buildListMock([vendorGroup]),
          createMock,
          buildListMock([vendorGroup, litigationGroup]),
        ]}
      />
    );

    await expect(page.getByTestId("corpus-groups-table")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await expect(page.getByText("Vendor Agreements")).toBeVisible({
      timeout: 20000,
    });
    // Member corpora preview and bound agent both render in the row.
    await expect(page.getByText("Contract Analyst")).toBeVisible({
      timeout: 20000,
    });

    await docScreenshot(page, "corpus-groups--management-panel--with-groups");

    await page.getByTestId("new-corpus-group-button").click();
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible({
      timeout: 20000,
    });

    await page
      .getByTestId("corpus-group-title-input")
      .fill("Litigation Bundle");
    await page.getByTestId("corpus-group-submit-button").click();

    // A successful create closes the modal and refetches the list.
    await expect(page.getByTestId("corpus-group-form-modal")).toHaveCount(0, {
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(2, {
      timeout: 20000,
    });
    await expect(page.getByText("Litigation Bundle")).toBeVisible({
      timeout: 20000,
    });
  });

  test("edits an existing group", async ({ mount, page }) => {
    const updateMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_GROUP,
        // The membership-replacement contract: ``corpusIds`` is the FULL set
        // seeded from the group's loaded edges, not a delta. ``slug`` is sent
        // because the seeded group has one; ``defaultAgentId`` is sent (not
        // ``clearDefaultAgent``) because the agent selection was left bound.
        variables: {
          corpusGroupId: GROUP_ID,
          title: "Vendor Agreements 2026",
          description: "Master services and vendor contracts.",
          corpusIds: [CORPUS_ID_MSA, CORPUS_ID_NDA],
          isPublic: true,
          corporaLimit: MEMBERSHIP_FETCH_LIMIT,
          slug: "vendor-agreements",
          defaultAgentId: AGENT_ID,
        },
      },
      result: {
        data: {
          updateCorpusGroup: {
            ok: true,
            message: "Updated",
            corpusGroup: renamedVendorGroup,
          },
        },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[
          buildListMock([vendorGroup]),
          updateMock,
          buildListMock([renamedVendorGroup]),
        ]}
      />
    );

    await expect(page.getByText("Vendor Agreements")).toBeVisible({
      timeout: 20000,
    });

    await page.getByRole("button", { name: "Edit Vendor Agreements" }).click();
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible({
      timeout: 20000,
    });
    // The form seeds itself from the row, including the slug.
    await expect(page.getByTestId("corpus-group-slug-input")).toHaveValue(
      "vendor-agreements",
      { timeout: 20000 }
    );

    await page
      .getByTestId("corpus-group-title-input")
      .fill("Vendor Agreements 2026");
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(page.getByTestId("corpus-group-form-modal")).toHaveCount(0, {
      timeout: 20000,
    });
    await expect(page.getByText("Vendor Agreements 2026")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
  });

  test("deletes a group after confirmation", async ({ mount, page }) => {
    const deleteMock: MockedResponse = {
      request: {
        query: DELETE_CORPUS_GROUP,
        variables: { corpusGroupId: GROUP_ID },
      },
      result: {
        data: { deleteCorpusGroup: { ok: true, message: "Deleted" } },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup]), deleteMock, buildListMock([])]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });

    // The row trigger is "Delete {title}"; the confirm button is a bare
    // "Delete", so the confirm lookup must be exact or it matches both.
    await page
      .getByRole("button", { name: "Delete Vendor Agreements" })
      .click();
    await expect(page.getByText("ARE YOU SURE?")).toBeVisible({
      timeout: 20000,
    });

    await page.getByRole("button", { name: "Delete", exact: true }).click();

    await expect(page.getByText("ARE YOU SURE?")).toHaveCount(0, {
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(0, {
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
  });
});
