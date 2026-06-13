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

const statusMock = (isSet: boolean, canSetup = true) => ({
  request: {
    query: GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
    variables: { corpusId: CORPUS_ID },
  },
  result: {
    data: {
      corpusIntelligenceSetupStatus: {
        referenceAvailable: true,
        referenceActionInstalled: isSet,
        installedTemplateNames: isSet
          ? ["Document Description Updater", "Document Summary Generator"]
          : [],
        missingTemplateNames: isSet
          ? []
          : ["Document Description Updater", "Document Summary Generator"],
        isFullySetUp: isSet,
        canSetup,
      },
    },
  },
});

const template = (overrides: Record<string, unknown> = {}) => ({
  templateName: "Document Description Updater",
  installedNow: true,
  alreadyInstalled: false,
  queuedCount: 12,
  skippedAlreadyRunCount: 0,
  error: "",
  remainingCount: 0,
  ...overrides,
});

// A successful setup payload. `summary` mirrors the full SETUP_CORPUS_INTELLIGENCE
// selection (including referenceActionAlreadyInstalled, which the real server
// returns) so the mock matches the server contract.
const setupResult = (summaryOverrides: Record<string, unknown> = {}) => ({
  setupCorpusIntelligence: {
    ok: true,
    message: "Collection intelligence setup started.",
    summary: {
      referenceAvailable: true,
      referenceActionInstalledNow: true,
      referenceActionAlreadyInstalled: false,
      referenceAnalysisStarted: true,
      totalActiveDocuments: 12,
      templates: [
        template(),
        template({ templateName: "Document Summary Generator" }),
      ],
      ...summaryOverrides,
    },
  },
});

const setupMockWith = (data: unknown) => ({
  request: {
    query: SETUP_CORPUS_INTELLIGENCE,
    variables: { corpusId: CORPUS_ID },
  },
  result: { data },
});

const setupMock = setupMockWith(setupResult());

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

  test("renders nothing for viewers who cannot run setup", async ({
    mount,
    page,
  }) => {
    // canSetup=false (read-only / anonymous viewer): the CTA would be a
    // guaranteed-to-fail button, so the banner must not render at all.
    const component = await mount(
      <MockedProvider
        mocks={[statusMock(false, false), statusMock(false, false)]}
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

  test("queued runs with a capped remainder report the deferred count", async ({
    mount,
    page,
  }) => {
    // A corpus larger than the per-call cap queues cap-many docs and defers
    // the rest — the toast must say so instead of implying full coverage.
    const component = await mount(
      <MockedProvider
        mocks={[
          statusMock(false),
          setupMockWith(
            setupResult({
              templates: [
                template({ queuedCount: 200, remainingCount: 50 }),
                template({
                  templateName: "Document Summary Generator",
                  queuedCount: 200,
                  remainingCount: 50,
                }),
              ],
            })
          ),
          statusMock(true),
        ]}
        addTypename={false}
      >
        <>
          <ToastContainer />
          <IntelligenceSetupBanner corpusId={CORPUS_ID} />
        </>
      </MockedProvider>
    );

    await page
      .locator('[data-testid="intelligence-setup-banner-button"]')
      .click();

    await expect(
      page.getByText(/400 document enrichment runs queued/i)
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/100 more deferred/i)).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("nothing-queued with a template error surfaces a soft warning", async ({
    mount,
    page,
  }) => {
    // ok=true but every run was capped/skipped and a template carried an error
    // → warning, not a "fully set up" claim. The banner stays (refetched status
    // is still not-fully-set-up).
    const component = await mount(
      <MockedProvider
        mocks={[
          statusMock(false),
          setupMockWith(
            setupResult({
              templates: [
                template({ installedNow: true, queuedCount: 0, error: "" }),
                template({
                  templateName: "Document Summary Generator",
                  installedNow: true,
                  queuedCount: 0,
                  error: "Batch run capped at 50 documents.",
                }),
              ],
            })
          ),
          statusMock(false),
        ]}
        addTypename={false}
      >
        <>
          <ToastContainer />
          <IntelligenceSetupBanner corpusId={CORPUS_ID} />
        </>
      </MockedProvider>
    );

    await page
      .locator('[data-testid="intelligence-setup-banner-button"]')
      .click();

    const warning = page.getByText(/some document runs couldn't be queued/i);
    await expect(warning).toBeVisible({ timeout: 10000 });
    // The actual per-template failure is surfaced, not a generic guess.
    await expect(
      page.getByText(/Batch run capped at 50 documents/i)
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("nothing-queued and no errors reports a clean set-up", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[
          statusMock(false),
          setupMockWith(
            setupResult({
              referenceAnalysisStarted: false,
              templates: [
                template({
                  installedNow: false,
                  alreadyInstalled: true,
                  queuedCount: 0,
                }),
                template({
                  templateName: "Document Summary Generator",
                  installedNow: false,
                  alreadyInstalled: true,
                  queuedCount: 0,
                }),
              ],
            })
          ),
          statusMock(true),
        ]}
        addTypename={false}
      >
        <>
          <ToastContainer />
          <IntelligenceSetupBanner corpusId={CORPUS_ID} />
        </>
      </MockedProvider>
    );

    await page
      .locator('[data-testid="intelligence-setup-banner-button"]')
      .click();

    await expect(
      page.getByText(/Collection intelligence is set up\./i)
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("a failed mutation surfaces an error toast and keeps the banner", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[
          statusMock(false),
          setupMockWith({
            setupCorpusIntelligence: {
              ok: false,
              message: "You don't have permission to set up this corpus.",
              summary: null,
            },
          }),
        ]}
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
    await page
      .locator('[data-testid="intelligence-setup-banner-button"]')
      .click();

    await expect(
      page.getByText(/don't have permission to set up this corpus/i)
    ).toBeVisible({ timeout: 10000 });
    // !ok returns before refetch → the banner is still offered.
    await expect(banner).toBeVisible();

    await component.unmount();
  });

  test("a network/mutation error surfaces the generic error toast", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[
          statusMock(false),
          {
            request: {
              query: SETUP_CORPUS_INTELLIGENCE,
              variables: { corpusId: CORPUS_ID },
            },
            error: new Error("network down"),
          },
        ]}
        addTypename={false}
      >
        <>
          <ToastContainer />
          <IntelligenceSetupBanner corpusId={CORPUS_ID} />
        </>
      </MockedProvider>
    );

    await page
      .locator('[data-testid="intelligence-setup-banner-button"]')
      .click();

    await expect(
      page.getByText(/Couldn't set up collection intelligence\./i)
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
