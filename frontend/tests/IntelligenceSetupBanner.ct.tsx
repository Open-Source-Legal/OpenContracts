/**
 * Component tests for IntelligenceSetupBanner — the one-click "set up
 * collection intelligence" CTA mounted inside IntelligencePanel. Hidden when
 * the bundle is fully installed; clicking fires the idempotent
 * setupCorpusIntelligence mutation and hides the banner once the refetched
 * status reports fully-set-up.
 *
 * NOTE: each JSX-component import is kept in its own ``import`` statement,
 * separate from all other imports, per the Playwright CT split-import rule.
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { ToastContainer } from "react-toastify";
import { IntelligenceSetupBanner } from "../src/components/corpuses/CorpusHome/intelligence/IntelligenceSetupBanner";
import { docScreenshot } from "./utils/docScreenshot";
import { GET_CORPUS_INTELLIGENCE_SETUP_STATUS } from "../src/graphql/queries";
import { SETUP_CORPUS_INTELLIGENCE } from "../src/graphql/mutations";

const CORPUS_ID = "Q29ycHVzVHlwZTox";

const statusMock = (isSet: boolean) => ({
  request: {
    query: GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusIntelligenceSetupStatus: {
        referenceActionInstalled: isSet,
        installedTemplateNames: isSet
          ? ["Document Description Updater", "Document Summary Generator"]
          : [],
        missingTemplateNames: isSet
          ? []
          : ["Document Description Updater", "Document Summary Generator"],
        isFullySetUp: isSet,
      },
    },
  },
});

const setupMock = {
  request: {
    query: SETUP_CORPUS_INTELLIGENCE,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      setupCorpusIntelligence: {
        ok: true,
        message: "Collection intelligence setup started.",
        summary: {
          referenceAvailable: true,
          referenceActionInstalledNow: true,
          referenceAnalysisStarted: true,
          totalActiveDocuments: 12,
          templates: [
            {
              templateName: "Document Description Updater",
              installedNow: true,
              alreadyInstalled: false,
              queuedCount: 12,
              skippedAlreadyRunCount: 0,
              error: "",
            },
            {
              templateName: "Document Summary Generator",
              installedNow: true,
              alreadyInstalled: false,
              queuedCount: 12,
              skippedAlreadyRunCount: 0,
              error: "",
            },
          ],
        },
      },
    },
  },
};

test.describe("IntelligenceSetupBanner", () => {
  test("offers setup when the bundle is missing, then hides after running it", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        // First status: not set up. After the mutation the banner refetches
        // and gets the fully-set-up status, hiding itself.
        mocks={[statusMock(false), setupMock, statusMock(true)]}
        addTypename={false}
      >
        <>
          <ToastContainer />
          <IntelligenceSetupBanner corpusId={CORPUS_ID} />
        </>
      </MockedProvider>
    );

    const banner = page.locator('[data-testid="intelligence-setup-banner"]');
    await expect(banner).toBeVisible({ timeout: 10000 });
    await expect(banner).toContainText("Set up collection intelligence");

    await docScreenshot(page, "corpus--intelligence-setup-banner--offer");

    await page
      .locator('[data-testid="intelligence-setup-banner-button"]')
      .click();

    // Success toast reports the queued enrichment fan-out.
    await expect(
      page.getByText(/24 document enrichment runs queued/i)
    ).toBeVisible({ timeout: 10000 });

    // Refetched status is fully-set-up → the banner disappears.
    await expect(banner).toHaveCount(0, { timeout: 10000 });

    await component.unmount();
  });

  test("renders nothing when the corpus is already fully set up", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[statusMock(true), statusMock(true)]}
        addTypename={false}
      >
        <IntelligenceSetupBanner corpusId={CORPUS_ID} />
      </MockedProvider>
    );

    await page.waitForTimeout(1000);
    await expect(
      page.locator('[data-testid="intelligence-setup-banner"]')
    ).toHaveCount(0);

    await component.unmount();
  });
});
