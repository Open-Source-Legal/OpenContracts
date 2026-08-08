// Playwright Component Test for the corpus re-embed migration control.
//
// ``updateCorpus`` refuses to change ``preferredEmbedder`` once a corpus holds
// documents (issue #437). Before this control the refusal named the
// ``reEmbedCorpus`` mutation, which the UI never exposed — so the only way out
// of the dialog was to put the original embedder back. These tests pin the
// control that closes that gap.
import React from "react";
import { MockedProvider } from "@apollo/client/testing";
// Playwright CT's babel transform only rewrites component references into
// ``importRefs`` when EVERY specifier in the statement is a JSX component.
// Keep this import on its own line — merging it with the query/mutation
// imports below leaves CorpusModal unrewritten and ``mount()`` throws.
import { CorpusModal } from "../src/components/corpuses/CorpusModal";
import { test, expect } from "./utils/coverage";
import { GET_EMBEDDERS } from "../src/graphql/queries";
import { RE_EMBED_CORPUS } from "../src/graphql/mutations";

const CORPUS_ID = "Q29ycHVzVHlwZTox";
const OLD_EMBEDDER = "opencontractserver.pipeline.embedders.old.OldEmbedder";
const NEW_EMBEDDER = "opencontractserver.pipeline.embedders.new.NewEmbedder";

const embeddersMock = {
  request: { query: GET_EMBEDDERS },
  result: {
    data: {
      pipelineComponents: {
        embedders: [
          {
            name: "OldEmbedder",
            moduleName: "old",
            title: "Old Embedder",
            description: "The embedder the corpus was built with",
            author: "OpenContracts",
            componentType: "EMBEDDER",
            inputSchema: {},
            vectorSize: 384,
            className: OLD_EMBEDDER,
            enabled: true,
          },
          {
            name: "NewEmbedder",
            moduleName: "new",
            title: "New Embedder",
            description: "A different embedder to migrate to",
            author: "OpenContracts",
            componentType: "EMBEDDER",
            inputSchema: {},
            vectorSize: 384,
            className: NEW_EMBEDDER,
            enabled: true,
          },
        ],
      },
    },
  },
  maxUsageCount: Number.POSITIVE_INFINITY,
};

const reEmbedMock = {
  request: {
    query: RE_EMBED_CORPUS,
    variables: { corpusId: CORPUS_ID, newEmbedder: NEW_EMBEDDER },
  },
  result: {
    data: {
      reEmbedCorpus: {
        ok: true,
        message: "Re-embedding started. The corpus will use 'New Embedder'.",
      },
    },
  },
};

const corpus = {
  id: CORPUS_ID,
  title: "Existing Corpus",
  slug: "existing-corpus",
  description: "A corpus that already holds documents",
  icon: null,
  labelSet: null,
  preferredEmbedder: OLD_EMBEDDER,
  categories: [],
  license: "CC_BY_4_0",
  licenseLink: "",
  myPermissions: ["read_corpus", "update_corpus"],
} as any;

/** Pick an embedder from the selector's dropdown by its visible label. */
async function selectEmbedder(page: any, label: string) {
  const heading = page.getByText("Preferred Embedder:", { exact: true });
  await heading.waitFor({ timeout: 15000 });
  // Scope to the selector's own wrapper. A bare ``combobox`` locator matches
  // the License dropdown first and silently opens the wrong menu, which then
  // fails on a missing option rather than on the real mistake.
  const control = heading.locator("xpath=..").getByRole("combobox").first();
  await control.click();
  await page.getByRole("listbox").getByText(label, { exact: false }).click();
}

test.describe("CorpusModal - embedder migration", () => {
  test("offers a re-embed action when the embedder changes on an existing corpus", async ({
    mount,
    page,
  }) => {
    await mount(
      <MockedProvider mocks={[embeddersMock, reEmbedMock]} addTypename={false}>
        <CorpusModal
          open={true}
          mode="EDIT"
          corpus={corpus}
          onClose={() => {}}
          onSubmit={() => {}}
        />
      </MockedProvider>
    );

    // No migration prompt until the selection actually differs — otherwise the
    // warning would greet every user who merely opened the dialog.
    await expect(page.getByTestId("corpus-reembed-notice")).toHaveCount(0);

    await selectEmbedder(page, "New Embedder");

    await expect(page.getByTestId("corpus-reembed-notice")).toBeVisible({
      timeout: 15000,
    });

    await page.getByTestId("corpus-reembed-button").click();

    // The message comes from the server, so asserting it proves the mutation
    // actually fired with the corpus id and the newly selected embedder --
    // a mock whose variables did not match would surface as a missing result.
    await expect(page.getByTestId("corpus-reembed-message")).toContainText(
      "Re-embedding started",
      { timeout: 15000 }
    );
  });
});
