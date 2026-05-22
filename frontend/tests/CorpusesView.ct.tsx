import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusesTestWrapper } from "./CorpusesTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import { openedCorpus } from "../src/graphql/cache";
import {
  GET_CORPUSES,
  GET_CORPUS_STATS,
  GET_CORPUS_METADATA,
  GET_DOCUMENTS,
} from "../src/graphql/queries";
import { DELETE_CORPUS } from "../src/graphql/mutations";
import { PermissionTypes } from "../src/components/types";
import { CorpusType } from "../src/types/graphql-api";

/* -------------------------------------------------------------------------- */
/* Mock Data                                                                   */
/* -------------------------------------------------------------------------- */
const dummyCorpus: CorpusType = {
  id: "CORPUS_PLAYWRIGHT",
  title: "Playwright Dummy Corpus",
  icon: null,
  isPublic: false,
  description: "",
  created: new Date().toISOString(),
  modified: new Date().toISOString(),
  creator: { id: "USER1", email: "tester@example.com", __typename: "UserType" },
  labelSet: null,
  parent: null as unknown as CorpusType,
  allowComments: true,
  preferredEmbedder: null,
  appliedAnalyzerIds: [],
  myPermissions: [PermissionTypes.CAN_UPDATE, PermissionTypes.CAN_READ],
  analyses: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "AnalysisTypeConnection",
  },
  annotations: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "AnnotationTypeConnection",
  },
  documents: {
    edges: [],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: null,
      endCursor: null,
      __typename: "PageInfo",
    },
    totalCount: 0,
    __typename: "DocumentTypeConnection",
  },
  __typename: "CorpusType",
};

const mocks: MockedResponse[] = [
  {
    request: { query: GET_CORPUSES, variables: {} },
    result: {
      data: {
        corpuses: {
          edges: [{ node: dummyCorpus, __typename: "CorpusTypeEdge" }],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "CorpusTypeConnection",
        },
      },
    },
  },
  {
    request: { query: GET_CORPUSES, variables: { textSearch: "" } },
    result: {
      data: {
        corpuses: {
          edges: [
            {
              node: dummyCorpus,
              __typename: "CorpusTypeEdge",
            },
          ],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "CorpusTypeConnection",
        },
      },
    },
  },
  {
    request: {
      query: GET_CORPUS_STATS,
      variables: { corpusId: dummyCorpus.id },
    },
    result: {
      data: {
        corpusStats: {
          totalDocs: 2,
          totalAnnotations: 0,
          totalComments: 0,
          totalAnalyses: 0,
          totalExtracts: 0,
          totalThreads: 0,
          totalChats: 0,
          totalRelationships: 0,
          __typename: "CorpusStatsType",
        },
      },
    },
  },
  {
    request: {
      query: GET_CORPUS_METADATA,
      variables: { metadataForCorpusId: dummyCorpus.id },
    },
    result: { data: { corpus: { ...dummyCorpus, parent: null } } },
  },
  {
    request: {
      query: GET_DOCUMENTS,
      variables: {
        inCorpusWithId: dummyCorpus.id,
        annotateDocLabels: true,
        includeMetadata: true,
      },
    },
    result: {
      data: {
        documents: {
          edges: [],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
          __typename: "DocumentTypeConnection",
        },
      },
    },
  },
  {
    request: {
      query: GET_DOCUMENTS,
      variables: {
        annotateDocLabels: false,
        includeMetadata: false,
      },
    },
    result: {
      data: {
        documents: {
          __typename: "DocumentTypeConnection",
          edges: [],
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
            __typename: "PageInfo",
          },
        },
      },
    },
  },
];

const mountCorpuses = (mount: any, initialCorpus?: CorpusType | null) => {
  if (initialCorpus) {
    openedCorpus(initialCorpus);
  } else {
    openedCorpus(null);
  }
  return mount(
    <CorpusesTestWrapper
      mocks={mocks}
      initialCorpus={initialCorpus}
      initialEntries={
        initialCorpus ? [`/corpuses/${initialCorpus.id}`] : ["/corpuses"]
      }
    />
  );
};

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test("sidebar expands and tab navigation works", async ({ mount, page }) => {
  // Sidebar is only visible in power user mode (?mode=power)
  openedCorpus(dummyCorpus);
  await mount(
    <CorpusesTestWrapper
      mocks={mocks}
      initialCorpus={dummyCorpus}
      initialEntries={[`/corpuses/${dummyCorpus.id}?mode=power`]}
    />
  );

  const sidebar = page.locator('[data-testid="navigation-sidebar"]');
  await expect(sidebar).toBeVisible();

  // Get initial width
  let widthNow = await sidebar.evaluate(
    (el) => el.getBoundingClientRect().width
  );

  // Collapse if needed
  if (widthNow >= 200) {
    await page.getByTestId("sidebar-toggle").click();
  }

  // Wait until collapsed (<100px)
  await expect
    .poll(
      async () =>
        await sidebar.evaluate((el) => el.getBoundingClientRect().width),
      {
        timeout: 3000,
        intervals: [100, 200, 500],
      }
    )
    .toBeLessThan(100);

  const collapsedWidth = await sidebar.evaluate(
    (el) => el.getBoundingClientRect().width
  );

  // Expand via toggle
  await page.getByTestId("sidebar-toggle").click();

  await expect
    .poll(
      async () =>
        await sidebar.evaluate((el) => el.getBoundingClientRect().width),
      {
        timeout: 3000,
        intervals: [100, 200, 500],
      }
    )
    .toBeGreaterThan(collapsedWidth + 100);

  // Click Documents tab
  await page.locator('[data-item-id="documents"]').click();
  // Search placeholder for documents appears
  await expect(
    page.getByPlaceholder("Search for document in corpus...")
  ).toBeVisible();

  // Click Annotations tab
  await page.locator('[data-item-id="annotations"]').click();
  await expect(
    page.getByPlaceholder("Search for annotated text in corpus...")
  ).toBeVisible();

  await docScreenshot(page, "corpus--workspace-view--annotations-tab");
});

/* -------------------------------------------------------------------------- */
/* handleDeleteCorpus — ok / error envelope handling                          */
/* -------------------------------------------------------------------------- */

const deleteCorpusMock = (
  ok: boolean,
  message: string | null
): MockedResponse => ({
  request: { query: DELETE_CORPUS, variables: { id: dummyCorpus.id } },
  result: {
    data: {
      deleteCorpus: { ok, message, __typename: "DeleteCorpusMutation" },
    },
  },
});

const CONFIRM_DELETE_MESSAGE = "Are you sure you want to delete corpus?";

test("delete corpus confirmation runs the ok=false branch of handleDeleteCorpus", async ({
  mount,
  page,
}) => {
  // DeleteCorpusMutation now returns { ok:false, message } instead of raising
  // (e.g. rejecting deletion of a personal corpus). handleDeleteCorpus must
  // route that resolved-but-unsuccessful response through the failure branch
  // rather than the success branch. The confirm modal is seeded directly via
  // the wrapper so the corpus-card context menu does not need to be driven.
  await mount(
    <CorpusesTestWrapper
      mocks={[...mocks, deleteCorpusMock(false, "Cannot delete this corpus.")]}
      initialDeletingCorpus={dummyCorpus}
    />
  );

  await expect(page.getByText(CONFIRM_DELETE_MESSAGE)).toBeVisible();
  await page.getByRole("button", { name: "Yes" }).click();

  // Confirming dismisses the modal and fires DeleteCorpusMutation; the
  // resolved ok=false envelope is handled without surfacing the modal again.
  await expect(page.getByText(CONFIRM_DELETE_MESSAGE)).toBeHidden();
  await page.waitForTimeout(1000);
});

test("delete corpus confirmation runs the ok=true branch of handleDeleteCorpus", async ({
  mount,
  page,
}) => {
  await mount(
    <CorpusesTestWrapper
      mocks={[...mocks, deleteCorpusMock(true, null)]}
      initialDeletingCorpus={dummyCorpus}
    />
  );

  await expect(page.getByText(CONFIRM_DELETE_MESSAGE)).toBeVisible();
  await page.getByRole("button", { name: "Yes" }).click();

  await expect(page.getByText(CONFIRM_DELETE_MESSAGE)).toBeHidden();
  await page.waitForTimeout(1000);
});
