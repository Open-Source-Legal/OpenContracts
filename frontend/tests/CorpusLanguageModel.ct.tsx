/**
 * Tests for the per-corpus Language Model card (Corpus.preferred_llm).
 *
 * Verifies that the card renders inside the Corpus Settings panel, surfaces the
 * registered provider chips, and shows the inherited system-default hint when
 * the corpus has no override of its own. Behavioural coverage of the save /
 * rollback flow lives in the Vitest unit test
 * (src/components/corpuses/__tests__/CorpusLanguageModelCard.test.tsx); this CT
 * exercises the card as mounted within the real settings panel and captures the
 * documentation screenshot.
 */

import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { CorpusSettingsTestWrapper } from "./CorpusSettingsTestWrapper";
import {
  GET_CORPUS_ACTIONS,
  GET_LLM_PROVIDERS,
  GET_SYSTEM_DEFAULT_LLM,
} from "../src/graphql/queries";
import { PermissionTypes } from "../src/components/types";

test.describe("Corpus Language Model Card", () => {
  const baseCorpus = {
    id: "Q29ycHVzVHlwZTox",
    title: "Test Corpus",
    description: "Test description",
    descriptionPreview: "Test description",
    allowComments: true,
    isPublic: false,
    slug: "test-corpus",
    // No override → the inherited system-default hint should render.
    preferredLlm: null,
    creator: {
      email: "owner@test.com",
      username: "owner",
      slug: "owner",
    },
  };

  const actionsMock = {
    request: {
      query: GET_CORPUS_ACTIONS,
      variables: { corpusId: baseCorpus.id },
    },
    result: {
      data: {
        corpusActions: {
          edges: [],
          pageInfo: { hasNextPage: false, endCursor: null },
        },
      },
    },
  };

  const providersMock = {
    request: { query: GET_LLM_PROVIDERS },
    result: {
      data: {
        pipelineComponents: {
          llmProviders: [
            {
              name: "anthropic",
              title: "Anthropic",
              className: "x.AnthropicProvider",
              providerKey: "anthropic",
              supportedModels: ["claude-opus-4-6"],
              requiresApiKey: true,
              enabled: true,
            },
          ],
        },
      },
    },
  };

  const defaultLlmMock = {
    request: { query: GET_SYSTEM_DEFAULT_LLM },
    result: { data: { pipelineSettings: { defaultLlm: "openai:gpt-4o" } } },
  };

  test("renders provider chips and the inherited-default hint", async ({
    mount,
    page,
  }) => {
    const corpus = {
      ...baseCorpus,
      myPermissions: [PermissionTypes.CAN_UPDATE, PermissionTypes.CAN_READ],
    };

    await mount(
      <CorpusSettingsTestWrapper
        mocks={[actionsMock, providersMock, defaultLlmMock]}
        corpus={corpus}
      />
    );

    // Card header is present.
    await expect(page.locator("#corpus-language-model-section")).toBeVisible();

    // The registered provider's suggested-model chip renders.
    await expect(
      page.getByRole("button", { name: "claude-opus-4-6" })
    ).toBeVisible();

    // With no override, the inherited system default surfaces in the hint.
    const hint = page.getByTestId("llm-inherited-hint");
    await expect(hint).toContainText("openai:gpt-4o");

    await docScreenshot(page, "corpus--language-model-card--inherit-default", {
      element: page.locator("#corpus-language-model-section"),
    });
  });
});
