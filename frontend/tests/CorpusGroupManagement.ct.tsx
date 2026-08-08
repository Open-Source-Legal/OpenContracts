import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import type { Page } from "@playwright/test";
// Split-import rule (CLAUDE.md pitfall #16): the mounted wrapper gets its own
// import statement, kept apart from the constant/helper imports below.
import { CorpusGroupManagementTestWrapper } from "./CorpusGroupManagementTestWrapper";
import {
  CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT,
  GET_MY_CORPUS_GROUPS,
  CREATE_CORPUS_GROUP,
  UPDATE_CORPUS_GROUP,
  DELETE_CORPUS_GROUP,
} from "../src/components/corpus_groups/graphql";
// The picker fixtures are shared verbatim with CorpusGroupSelectors.ct.tsx, so
// the ids/titles this panel's mutations assert on are the same ones the pickers
// are proven to emit — no second, drift-prone copy of the same corpus set. Only
// the plain constants are imported here; the mock arrays themselves are wired
// in by the wrapper via ``pickerData`` (their variableMatcher callbacks cannot
// survive the Node→browser prop serialization).
import {
  CORPUS_ID_MSA,
  CORPUS_ID_NDA,
  CORPUS_TITLE_MSA,
  CORPUS_TITLE_NDA,
  AGENT_ID_ANALYST,
  AGENT_NAME_ANALYST,
} from "./CorpusGroupPickerFixtures";
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
const AGENT_ID = AGENT_ID_ANALYST;

const LIST_VARIABLES = {
  // ``mine: false`` — the panel lists every group the viewer can see, not just
  // the ones they created, so a public or shared group is reachable by the
  // collaborators it exists for. Ownership gates the row actions instead.
  // These mocks must match the variables EXACTLY: pinned to ``mine: true`` the
  // query silently stops matching and the panel renders its empty state.
  mine: false,
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
 * mutation ever leaving the component. The dedicated truncation test below
 * uses ``truncatedGroup`` to exercise exactly that refusal.
 */
const vendorGroup = {
  id: GROUP_ID,
  title: "Vendor Agreements",
  slug: "vendor-agreements",
  description: "Master services and vendor contracts.",
  isPublic: true,
  created: "2026-07-01T12:00:00+00:00",
  modified: "2026-07-02T12:00:00+00:00",
  creator: { id: "user-1", displayName: "member" },
  defaultAgent: { id: AGENT_ID, name: AGENT_NAME_ANALYST },
  corpora: {
    totalCount: 2,
    edges: [
      { node: { id: CORPUS_ID_MSA, title: CORPUS_TITLE_MSA } },
      { node: { id: CORPUS_ID_NDA, title: CORPUS_TITLE_NDA } },
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
  creator: { id: "user-1", displayName: "member" },
  defaultAgent: null,
  corpora: { totalCount: 0, edges: [] },
};

const renamedVendorGroup = {
  ...vendorGroup,
  title: "Vendor Agreements 2026",
};

/**
 * A group whose server-side membership exceeds what the page loaded. Saving it
 * would drop the three unseen members, so ``handleSubmit`` must refuse.
 */
const truncatedGroup = {
  ...vendorGroup,
  corpora: { ...vendorGroup.corpora, totalCount: 5 },
};

/* -------------------------------------------------------------------------- */
/* Mock builders                                                               */
/* -------------------------------------------------------------------------- */

/**
 * The list query is fired once on mount (``cache-and-network`` over an empty
 * cache) and once more per ``refetch()``. MockLink serves identically-keyed
 * mocks in array order, so a mutation test supplies ``[listBefore, mutation,
 * listAfter]`` and the refetch picks up the post-mutation state.
 *
 * ``totalCount`` defaults to the number of supplied groups — pass a larger one
 * to model a server-capped page, which the panel must warn about.
 */
const buildListMock = (
  groups: unknown[],
  totalCount?: number
): MockedResponse => ({
  request: { query: GET_MY_CORPUS_GROUPS, variables: LIST_VARIABLES },
  result: {
    data: {
      corpusGroups: {
        totalCount: totalCount ?? groups.length,
        edges: groups.map((node) => ({ node })),
      },
    },
  },
});

/**
 * Failure mocks are expressed as GraphQL errors rather than MockedResponse's
 * ``error: new Error(...)``.
 *
 * Mocks reach the component as Playwright mount PROPS, which are serialized
 * from the Node realm into the browser. An ``Error`` instance does not survive
 * that trip — it arrives as an empty object, Apollo finds neither a network
 * error nor graphQLErrors, and the component renders the useless placeholder
 * "Error message not found." instead of the message the test asserts on. A
 * plain ``errors`` array is data, so it crosses intact and still produces the
 * ``ApolloError`` that drives both the query's error branch and each mutation's
 * ``onError`` handler.
 */
const graphqlErrorResult = (message: string) => ({
  errors: [{ message }],
});

const buildListErrorMock = (message: string): MockedResponse => ({
  request: { query: GET_MY_CORPUS_GROUPS, variables: LIST_VARIABLES },
  result: graphqlErrorResult(message),
});

/* -------------------------------------------------------------------------- */
/* Interaction helpers                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Open the create modal and fill in a title.
 *
 * The title is asserted to have landed BEFORE any submit: the ``Input`` is
 * controlled by React state, and ``handleSubmit`` reads that state — not the
 * DOM. Clicking submit while the state update is still in flight would take
 * the "title is required" validation branch and look exactly like a product
 * bug. Waiting on the rendered value is the visible evidence that the state
 * behind it has caught up.
 */
const openCreateModalWithTitle = async (page: Page, title: string) => {
  await page.getByTestId("new-corpus-group-button").click();
  await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible({
    timeout: 20000,
  });
  await page.getByTestId("corpus-group-title-input").fill(title);
  await expect(page.getByTestId("corpus-group-title-input")).toHaveValue(
    title,
    {
      timeout: 20000,
    }
  );
};

/** Same guarantee as above, for the edit modal opened from a row. */
const openEditModal = async (page: Page, rowTitle: string) => {
  await page.getByRole("button", { name: `Edit ${rowTitle}` }).click();
  await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible({
    timeout: 20000,
  });
};

/** Pick the first menu entry matching ``label`` from one of the two pickers. */
const pickFromSelector = async (page: Page, root: string, label: string) => {
  await page.getByTestId(root).locator(".react-select__control").click();
  const option = page
    .getByTestId(root)
    .locator(".react-select__option")
    .filter({ hasText: label });
  await expect(option).toBeVisible({ timeout: 20000 });
  await option.click();
};

test.describe("CorpusGroupManagement", () => {
  /* ------------------------------------------------------------------ */
  /* Identity branches                                                   */
  /* ------------------------------------------------------------------ */

  /**
   * Anonymous viewers must get the prompt AND cause no fetch. The mock list is
   * deliberately EMPTY: if the query were not skipped, MockedProvider would
   * fail it for want of a matching mock and the panel would render its
   * error branch instead — so the absence of that error is what proves the
   * skip, not merely the presence of the prompt.
   */
  test("prompts anonymous viewers to sign in and skips the list query", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper mocks={[]} auth="anonymous" />
    );

    // The pre-effect first paint renders this same prompt, so wait for the
    // seeding marker before concluding anything about the anonymous branch.
    await expect(page.getByTestId("auth-seeded")).toBeAttached({
      timeout: 20000,
    });
    await expect(page.getByText("Sign in to manage corpus groups")).toBeVisible(
      { timeout: 20000 }
    );
    await expect(page.getByTestId("corpus-groups-table")).toHaveCount(0);
    await expect(page.getByTestId("corpus-groups-empty-state")).toHaveCount(0);
    await expect(page.getByText("Error loading corpus groups")).toHaveCount(0);

    await docScreenshot(page, "corpus-groups--management-panel--anonymous");
  });

  /**
   * A bearer token exists but GET_ME has not landed. Deriving "anonymous" from
   * the user object alone would flash the sign-in prompt at every authenticated
   * user who hard-navigates here, so this state must resolve to a spinner.
   */
  test("shows a loading state while the identity round trip is in flight", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper mocks={[]} auth="resolving" />
    );

    await expect(page.getByText("Loading corpus groups...")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("Sign in to manage corpus groups")).toHaveCount(
      0
    );
  });

  /* ------------------------------------------------------------------ */
  /* List rendering                                                      */
  /* ------------------------------------------------------------------ */

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

  /** Nothing to show plus an error: the error takes over the whole page. */
  test("shows a full-page error when the list fails with nothing loaded", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListErrorMock("Backend unavailable")]}
      />
    );

    await expect(page.getByText("Error loading corpus groups")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("Backend unavailable")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-groups-table")).toHaveCount(0);
  });

  /**
   * The asymmetry with the test above: once rows exist, a failed REFETCH must
   * not discard them. The user may be mid-task, so the failure is reported
   * non-destructively in a banner and the table stays put.
   */
  test("keeps the rows and warns when a refetch fails", async ({
    mount,
    page,
  }) => {
    const deleteMock: MockedResponse = {
      request: {
        query: DELETE_CORPUS_GROUP,
        variables: { corpusGroupId: GROUP_ID },
      },
      result: { data: { deleteCorpusGroup: { ok: true, message: "Deleted" } } },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[
          buildListMock([vendorGroup]),
          deleteMock,
          buildListErrorMock("Refresh failed"),
        ]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });

    // A successful delete triggers the refetch that we make fail.
    await page
      .getByRole("button", { name: "Delete Vendor Agreements" })
      .click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();

    await expect(page.getByText("Could not refresh corpus groups")).toBeVisible(
      { timeout: 20000 }
    );
    // The rows survived — this is the whole point of the branch.
    await expect(page.getByTestId("corpus-groups-table")).toBeVisible();
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1);
  });

  /** The connection is server-capped; a silently short list would mislead. */
  test("warns when the list is truncated", async ({ mount, page }) => {
    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup], 7)]}
      />
    );

    await expect(page.getByText("List truncated")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("Showing 1 of 7 corpus groups.")).toBeVisible({
      timeout: 20000,
    });
    // The warning supplements the table rather than replacing it.
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1);
  });

  test("shows another user's group read-only, with no edit or delete", async ({
    mount,
    page,
  }) => {
    // The panel lists every group the viewer can SEE, so a public group owned
    // by someone else appears here. It must be unmistakably read-only: the row
    // actions are ownership-gated (the mutations are permission-gated
    // server-side regardless, but offering a button that always fails is not a
    // UI we want).
    const foreignGroup = {
      ...vendorGroup,
      id: "Q29ycHVzR3JvdXBUeXBlOjk5",
      title: "Someone Else's Bundle",
      slug: "someone-elses-bundle",
      creator: { id: "user-2", displayName: "other-person" },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup, foreignGroup])]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(2, {
      timeout: 20000,
    });

    // The viewer's own group keeps its actions...
    await expect(
      page.getByRole("button", { name: "Edit Vendor Agreements" })
    ).toBeVisible({ timeout: 20000 });

    // ...and the foreign one has none, showing the owner instead.
    await expect(
      page.getByRole("button", { name: "Edit Someone Else's Bundle" })
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Delete Someone Else's Bundle" })
    ).toHaveCount(0);
    await expect(page.getByText("other-person")).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByText("Read-only")).toHaveCount(1);
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
    await expect(page.getByText(AGENT_NAME_ANALYST)).toBeVisible({
      timeout: 20000,
    });

    await docScreenshot(page, "corpus-groups--management-panel--with-groups");

    await openCreateModalWithTitle(page, "Litigation Bundle");
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

  /* ------------------------------------------------------------------ */
  /* Client-side validation                                              */
  /* ------------------------------------------------------------------ */

  /**
   * No CREATE mock is supplied on purpose. If validation let the mutation
   * through, MockedProvider would raise "No more mocked responses" rather than
   * letting the test pass on a lucky assertion.
   */
  test("rejects a whitespace-only title without firing a mutation", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper mocks={[buildListMock([])]} />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
    // Whitespace, not empty: the guard trims before testing for emptiness.
    await openCreateModalWithTitle(page, "   ");
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(page.getByText("Group title is required")).toBeVisible({
      timeout: 20000,
    });
    // The modal is still open, so the user's input was not thrown away.
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  test("rejects a slug with illegal characters without firing a mutation", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper mocks={[buildListMock([])]} />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
    await openCreateModalWithTitle(page, "Litigation Bundle");

    // Spaces and punctuation both fall outside Django's SlugField character
    // class, which this guard mirrors.
    await page.getByTestId("corpus-group-slug-input").fill("bad slug!");
    await expect(page.getByTestId("corpus-group-slug-input")).toHaveValue(
      "bad slug!",
      { timeout: 20000 }
    );
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(
      page.getByText(
        "Slug may only contain letters, numbers, hyphens and underscores"
      )
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  /**
   * ``updateCorpusGroup`` REPLACES membership from the form's seeded edges, so
   * submitting a group whose page was capped would silently delete the members
   * that were never loaded. The panel must refuse rather than mutate.
   */
  test("refuses to save a group whose membership was truncated", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([truncatedGroup])]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await openEditModal(page, "Vendor Agreements");
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(
      page.getByText("This group has 5 corpora but only 2 loaded")
    ).toBeVisible({ timeout: 20000 });
    // No UPDATE mock exists — reaching the mutation would fail the test loudly.
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  /* ------------------------------------------------------------------ */
  /* Create — full form                                                  */
  /* ------------------------------------------------------------------ */

  /**
   * Drives every field the create branch can populate, including both pickers
   * and the visibility switch, so the optional-argument rules (slug and
   * defaultAgentId are sent only when set) are covered in their "set" form —
   * the list test above covers the omitted form.
   */
  test("creates a group with a slug, description, corpora, agent and public visibility", async ({
    mount,
    page,
  }) => {
    const createMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_GROUP,
        variables: {
          title: "Litigation Bundle",
          description: "Everything for the active matters.",
          corpusIds: [CORPUS_ID_MSA],
          isPublic: true,
          corporaLimit: MEMBERSHIP_FETCH_LIMIT,
          slug: "litigation-bundle",
          defaultAgentId: AGENT_ID,
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
          buildListMock([]),
          createMock,
          buildListMock([litigationGroup]),
        ]}
        pickerData
      />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
    await openCreateModalWithTitle(page, "Litigation Bundle");

    await page.getByTestId("corpus-group-slug-input").fill("litigation-bundle");
    await page
      .locator("#corpus-group-description")
      .fill("Everything for the active matters.");
    await pickFromSelector(page, "corpus-multi-select", CORPUS_TITLE_MSA);
    await pickFromSelector(
      page,
      "agent-configuration-select",
      AGENT_NAME_ANALYST
    );
    await page.locator("label.oc-toggle-wrapper").click();

    // Every field is confirmed landed before submitting — see
    // ``openCreateModalWithTitle`` for why the DOM value is the gate.
    await expect(page.getByTestId("corpus-group-slug-input")).toHaveValue(
      "litigation-bundle"
    );
    await expect(page.locator("#corpus-group-description")).toHaveValue(
      "Everything for the active matters."
    );
    await expect(page.getByRole("switch")).toBeChecked();
    await expect(
      page.getByTestId("corpus-multi-select").getByText(CORPUS_TITLE_MSA)
    ).toBeVisible();
    await expect(
      page
        .getByTestId("agent-configuration-select")
        .getByText(AGENT_NAME_ANALYST)
    ).toBeVisible();

    await page.getByTestId("corpus-group-submit-button").click();

    await expect(page.getByTestId("corpus-group-form-modal")).toHaveCount(0, {
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
  });

  /* ------------------------------------------------------------------ */
  /* Create — failure paths                                              */
  /* ------------------------------------------------------------------ */

  /**
   * A resolved-but-unsuccessful mutation. The modal must STAY open: the
   * server rejected the input, so the user needs it back to fix it.
   */
  test("surfaces a create failure reported as ok: false", async ({
    mount,
    page,
  }) => {
    const createMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_GROUP,
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
            ok: false,
            message: "A group with that slug already exists",
            corpusGroup: null,
          },
        },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([]), createMock]}
      />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
    await openCreateModalWithTitle(page, "Litigation Bundle");
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(
      page.getByText("A group with that slug already exists")
    ).toBeVisible({ timeout: 20000 });
    // No refetch was queued either — only the success path refetches.
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  /** The transport failed outright — a different handler from ok: false. */
  test("surfaces a create network error", async ({ mount, page }) => {
    const createMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_GROUP,
        variables: {
          title: "Litigation Bundle",
          description: "",
          corpusIds: [],
          isPublic: false,
          corporaLimit: MEMBERSHIP_FETCH_LIMIT,
        },
      },
      result: graphqlErrorResult("Create transport down"),
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([]), createMock]}
      />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });
    await openCreateModalWithTitle(page, "Litigation Bundle");
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(
      page.getByText("Error creating corpus group: Create transport down")
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  /* ------------------------------------------------------------------ */
  /* Update                                                              */
  /* ------------------------------------------------------------------ */

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

    await openEditModal(page, "Vendor Agreements");
    // The form seeds itself from the row, including the slug.
    await expect(page.getByTestId("corpus-group-slug-input")).toHaveValue(
      "vendor-agreements",
      { timeout: 20000 }
    );

    await page
      .getByTestId("corpus-group-title-input")
      .fill("Vendor Agreements 2026");
    await expect(page.getByTestId("corpus-group-title-input")).toHaveValue(
      "Vendor Agreements 2026",
      { timeout: 20000 }
    );
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

  /**
   * Clearing the agent picker must send ``clearDefaultAgent: true`` and NOT a
   * null ``defaultAgentId`` — the two arguments are mutually exclusive
   * server-side, and the unbind is deliberately unconditional so the clear
   * button still works when a bound agent has merely become unreadable.
   */
  test("sends clearDefaultAgent when the agent picker is cleared", async ({
    mount,
    page,
  }) => {
    const updateMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_GROUP,
        variables: {
          corpusGroupId: GROUP_ID,
          title: "Vendor Agreements",
          description: "Master services and vendor contracts.",
          corpusIds: [CORPUS_ID_MSA, CORPUS_ID_NDA],
          isPublic: true,
          corporaLimit: MEMBERSHIP_FETCH_LIMIT,
          slug: "vendor-agreements",
          clearDefaultAgent: true,
        },
      },
      result: {
        data: {
          updateCorpusGroup: {
            ok: true,
            message: "Updated",
            corpusGroup: { ...vendorGroup, defaultAgent: null },
          },
        },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[
          buildListMock([vendorGroup]),
          updateMock,
          buildListMock([{ ...vendorGroup, defaultAgent: null }]),
        ]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await openEditModal(page, "Vendor Agreements");

    // The bound agent is seeded from the row, not from a search.
    await expect(
      page
        .getByTestId("agent-configuration-select")
        .getByText(AGENT_NAME_ANALYST)
    ).toBeVisible({ timeout: 20000 });

    await page
      .getByTestId("agent-configuration-select")
      .locator(".react-select__clear-indicator")
      .click();
    await expect(
      page
        .getByTestId("agent-configuration-select")
        .getByText(AGENT_NAME_ANALYST)
    ).toHaveCount(0, { timeout: 20000 });

    await page.getByTestId("corpus-group-submit-button").click();

    // The modal only closes on a successful mutation, so its disappearance is
    // proof the variables above matched exactly.
    await expect(page.getByTestId("corpus-group-form-modal")).toHaveCount(0, {
      timeout: 20000,
    });
  });

  test("surfaces an update failure reported as ok: false", async ({
    mount,
    page,
  }) => {
    const updateMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_GROUP,
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
            ok: false,
            message: "You no longer have permission to edit this group",
            corpusGroup: null,
          },
        },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup]), updateMock]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await openEditModal(page, "Vendor Agreements");
    await page
      .getByTestId("corpus-group-title-input")
      .fill("Vendor Agreements 2026");
    await expect(page.getByTestId("corpus-group-title-input")).toHaveValue(
      "Vendor Agreements 2026",
      { timeout: 20000 }
    );
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(
      page.getByText("You no longer have permission to edit this group")
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  test("surfaces an update network error", async ({ mount, page }) => {
    const updateMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_GROUP,
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
      result: graphqlErrorResult("Update transport down"),
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup]), updateMock]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await openEditModal(page, "Vendor Agreements");
    await page
      .getByTestId("corpus-group-title-input")
      .fill("Vendor Agreements 2026");
    await expect(page.getByTestId("corpus-group-title-input")).toHaveValue(
      "Vendor Agreements 2026",
      { timeout: 20000 }
    );
    await page.getByTestId("corpus-group-submit-button").click();

    await expect(
      page.getByText("Error updating corpus group: Update transport down")
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("corpus-group-form-modal")).toBeVisible();
  });

  /* ------------------------------------------------------------------ */
  /* Delete                                                              */
  /* ------------------------------------------------------------------ */

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

  /**
   * The confirm dialog opts into caller-controlled close (``confirmLoading``),
   * so it does NOT dismiss itself on "Yes". Every delete outcome must clear the
   * pending group or the dialog is stranded on screen with a dead spinner —
   * which is why both failure paths assert the dismissal, not just the toast.
   */
  test("surfaces a delete failure reported as ok: false and dismisses the confirmation", async ({
    mount,
    page,
  }) => {
    const deleteMock: MockedResponse = {
      request: {
        query: DELETE_CORPUS_GROUP,
        variables: { corpusGroupId: GROUP_ID },
      },
      result: {
        data: {
          deleteCorpusGroup: {
            ok: false,
            message: "Group is still referenced by an active conversation",
          },
        },
      },
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup]), deleteMock]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await page
      .getByRole("button", { name: "Delete Vendor Agreements" })
      .click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();

    await expect(
      page.getByText("Group is still referenced by an active conversation")
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("ARE YOU SURE?")).toHaveCount(0, {
      timeout: 20000,
    });
    // Nothing was deleted, so the row must still be there.
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1);
  });

  test("surfaces a delete network error and dismisses the confirmation", async ({
    mount,
    page,
  }) => {
    const deleteMock: MockedResponse = {
      request: {
        query: DELETE_CORPUS_GROUP,
        variables: { corpusGroupId: GROUP_ID },
      },
      result: graphqlErrorResult("Delete transport down"),
    };

    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup]), deleteMock]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await page
      .getByRole("button", { name: "Delete Vendor Agreements" })
      .click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();

    await expect(
      page.getByText("Error deleting corpus group: Delete transport down")
    ).toBeVisible({ timeout: 20000 });
    await expect(page.getByText("ARE YOU SURE?")).toHaveCount(0, {
      timeout: 20000,
    });
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1);
  });

  /** Cancelling clears the pending group via toggleModal; noAction is a no-op. */
  test("cancels a pending delete without mutating", async ({ mount, page }) => {
    await mount(
      <CorpusGroupManagementTestWrapper
        mocks={[buildListMock([vendorGroup])]}
      />
    );

    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1, {
      timeout: 20000,
    });
    await page
      .getByRole("button", { name: "Delete Vendor Agreements" })
      .click();
    await expect(page.getByText("ARE YOU SURE?")).toBeVisible({
      timeout: 20000,
    });

    await page.getByRole("button", { name: "No", exact: true }).click();

    await expect(page.getByText("ARE YOU SURE?")).toHaveCount(0, {
      timeout: 20000,
    });
    // No DELETE mock exists, so a mutation here would fail the test loudly.
    await expect(page.getByTestId("corpus-group-row")).toHaveCount(1);
  });

  /* ------------------------------------------------------------------ */
  /* Modal dismissal                                                     */
  /* ------------------------------------------------------------------ */

  /**
   * Three independent close affordances reach three different handlers:
   * escape/overlay via the Modal's own ``onClose``, the header X, and the
   * footer Cancel. None of them may mutate — no mutation mock is supplied.
   */
  test("dismisses the form modal via escape, the header close and cancel", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusGroupManagementTestWrapper mocks={[buildListMock([])]} />
    );

    await expect(page.getByTestId("corpus-groups-empty-state")).toBeVisible({
      timeout: 20000,
    });

    const modal = page.getByTestId("corpus-group-form-modal");

    await page.getByTestId("new-corpus-group-button").click();
    await expect(modal).toBeVisible({ timeout: 20000 });
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0, { timeout: 20000 });

    await page.getByTestId("new-corpus-group-button").click();
    await expect(modal).toBeVisible({ timeout: 20000 });
    await page.getByRole("button", { name: "Close" }).click();
    await expect(modal).toHaveCount(0, { timeout: 20000 });

    await page.getByTestId("new-corpus-group-button").click();
    await expect(modal).toBeVisible({ timeout: 20000 });
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(modal).toHaveCount(0, { timeout: 20000 });
  });
});
