/**
 * Component tests for the corpus-intelligence CAML embeds — specifically the
 * ambient-context wiring (CamlEmbedContext). The underlying panel/graph/chips
 * are covered by their own component tests; here we verify the embeds read the
 * context and that ask-across-docs routes to the context's chat handler.
 *
 * NOTE: each JSX-component import is kept in its own statement, separate from
 * helper imports, per the Playwright CT split-import rule.
 */
import { test, expect } from "./utils/coverage";
import { AskAcrossDocsEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/AskAcrossDocsEmbed";
import { CamlEmbedProvider } from "../src/components/corpuses/caml/CamlEmbedContext";

test.describe("CAML intelligence embeds", () => {
  test("ask-across-docs renders chips and routes to the context chat handler", async ({
    mount,
    page,
  }) => {
    const submitted: string[] = [];

    const component = await mount(
      <CamlEmbedProvider
        value={{
          corpusId: "Q29ycHVzVHlwZTox",
          onAskQuestion: (q) => {
            submitted.push(q);
          },
        }}
      >
        <AskAcrossDocsEmbed />
      </CamlEmbedProvider>
    );

    const chip = page
      .locator('[data-testid="ask-across-docs-suggestion"]')
      .first();
    await expect(chip).toBeVisible({ timeout: 10000 });
    await chip.click();
    await expect.poll(() => submitted.length).toBeGreaterThan(0);

    await component.unmount();
  });

  test("ask-across-docs renders nothing without a chat handler", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CamlEmbedProvider value={{ corpusId: "Q29ycHVzVHlwZTox" }}>
        <AskAcrossDocsEmbed />
      </CamlEmbedProvider>
    );

    await expect(
      page.locator('[data-testid="ask-across-docs-suggestions"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
