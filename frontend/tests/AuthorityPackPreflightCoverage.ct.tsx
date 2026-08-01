/**
 * Additional coverage for the Authority Packs catalog tab and its preflight
 * modal, layered on top of AuthorityPacks.ct.tsx. That file exercises the
 * primary happy paths through the full AuthorityConsole shell; this file
 * targets branches the console shell can't reach on its own (no
 * onImportCorpus bridge) plus catalog/preflight loading, error, empty, and
 * failure states that the happy-path tests never trigger:
 *  - the pack catalog's own loading / error / empty / refresh states
 *  - card-level fallback text (blank displayName/description/validationError,
 *    singular "1 declared source host")
 *  - every packStatus() badge (fully public, partially public, partially
 *    installed, available)
 *  - approvalTone()'s neutral and review-only branches
 *  - every pack-summary badge inside the preflight modal (fully public,
 *    partially public, partially installed)
 *  - the preflight query's own loading / error / null-pack states
 *  - install failure (ok:false, with and without a server message), a thrown
 *    network error, and a successful publish that falls back to the default
 *    toast message
 *  - the close-blocked-while-installing guard
 *  - PacksTab mounted without a corpus-ZIP-importer bridge
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";

import { PacksTabTestWrapper } from "./PacksTabTestWrapper";

import {
  GET_AUTHORITY_PACKS,
  GET_AUTHORITY_PACK_PREFLIGHT,
} from "../src/graphql/queries";
import { INSTALL_AUTHORITY_PACK } from "../src/graphql/mutations";

const corpus = (over: Record<string, unknown> = {}) => ({
  corpusId: null,
  slug: "texas-electric-law",
  title: "Texas Electric Law",
  approvalStatus: "pending_legal_review",
  installed: false,
  isPublic: false,
  ...over,
});

const pack = (over: Record<string, unknown> = {}) => ({
  id: "texas-electric",
  name: "texas_electric_law",
  displayName: "Texas Electric Law",
  description: "Texas statutes and regulations for the electric grid.",
  jurisdiction: "us-tx",
  schemaVersion: 2,
  fingerprint: "sha256:pack-v1",
  sourceHosts: ["statutes.capitol.texas.gov", "texreg.sos.state.tx.us"],
  valid: true,
  validationError: null,
  approvalStatus: "pending_legal_review",
  canInstall: true,
  canPublish: false,
  installedCount: 0,
  publicCount: 0,
  totalCorpora: 2,
  installed: false,
  fullyPublic: false,
  corpora: [
    corpus(),
    corpus({ slug: "puct-electric", title: "PUCT Electric Rules" }),
  ],
  ...over,
});

const packsMock = (packs: ReturnType<typeof pack>[]) => ({
  request: { query: GET_AUTHORITY_PACKS },
  result: { data: { authorityPacks: packs } },
});

const preflightMock = (preflight: ReturnType<typeof pack>) => ({
  request: {
    query: GET_AUTHORITY_PACK_PREFLIGHT,
    variables: { packId: preflight.id },
  },
  result: { data: { authorityPackPreflight: preflight } },
});

test.describe("Authority packs catalog states", () => {
  test("shows a loading state before the pack catalog resolves", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <PacksTabTestWrapper mocks={[{ ...packsMock([pack()]), delay: 400 }]} />
    );

    await expect(page.getByText("Loading authority packs…")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="pack-card"]')).toHaveCount(1, {
      timeout: 15000,
    });

    await docScreenshot(page, "admin--authority-packs-tab--loading");
    await component.unmount();
  });

  test("shows an error state when the pack catalog fails to load", async ({
    mount,
    page,
  }) => {
    const errorMock = {
      request: { query: GET_AUTHORITY_PACKS },
      error: new Error("Could not reach the authority pack service."),
    };
    const component = await mount(<PacksTabTestWrapper mocks={[errorMock]} />);

    // MockedProvider surfaces network-error mocks through Apollo's own
    // (production-minified) error-message decoder, which renders as
    // "Error message not found." rather than the injected Error's own
    // message in this test environment — so this only asserts the
    // component's own error heading and that the catalog itself never
    // rendered, not the exact injected message text.
    await expect(page.getByText("Could not load authority packs")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="packs-catalog"]')).toHaveCount(0);

    await docScreenshot(page, "admin--authority-packs-tab--catalog-error");
    await component.unmount();
  });

  test("shows an empty state when no packs are configured", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <PacksTabTestWrapper mocks={[packsMock([])]} />
    );

    await expect(page.getByText("No authority packs available")).toBeVisible({
      timeout: 15000,
    });

    await docScreenshot(page, "admin--authority-packs-tab--empty-catalog");
    await component.unmount();
  });

  test("refetches the catalog when Refresh is clicked", async ({
    mount,
    page,
  }) => {
    const before = pack();
    const after = pack({ displayName: "Texas Electric Law (Refreshed)" });
    const component = await mount(
      <PacksTabTestWrapper mocks={[packsMock([before]), packsMock([after])]} />
    );

    await expect(page.getByText("Texas Electric Law").first()).toBeVisible({
      timeout: 15000,
    });
    await page.locator('[data-testid="packs-refresh"]').click();
    await expect(page.getByText("Texas Electric Law (Refreshed)")).toBeVisible({
      timeout: 15000,
    });

    await component.unmount();
  });

  test("falls back to catalog defaults for blank fields and singularizes a lone source host", async ({
    mount,
    page,
  }) => {
    const blankPack = pack({
      id: "blank-pack",
      name: "blank_pack",
      displayName: "",
      description: "",
      valid: false,
      validationError: null,
      canInstall: false,
      sourceHosts: ["only-host.example.gov"],
    });
    const component = await mount(
      <PacksTabTestWrapper mocks={[packsMock([blankPack])]} />
    );

    await expect(page.locator('[data-testid="pack-card"]')).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.getByRole("heading", { name: "blank_pack" })
    ).toBeVisible();
    await expect(page.getByText("No pack description provided.")).toBeVisible();
    await expect(page.getByText("Manifest validation failed.")).toBeVisible();
    await expect(page.getByText("1 declared source host")).toBeVisible();

    await docScreenshot(page, "admin--authority-packs-tab--blank-fields");
    await component.unmount();
  });

  test("shows every catalog status badge across the pack list", async ({
    mount,
    page,
  }) => {
    // Display names deliberately avoid the words used by packStatus()'s own
    // badge labels ("Fully public", "Partially public", …) so `getByText`
    // (case-insensitive substring matching) can't match both the card title
    // and its status badge at once.
    const fullyPublicPack = pack({
      id: "fully-public",
      displayName: "Alpha Catalog Pack",
      fullyPublic: true,
      publicCount: 2,
      installed: true,
      installedCount: 2,
    });
    const partiallyPublicPack = pack({
      id: "partially-public",
      displayName: "Bravo Catalog Pack",
      fullyPublic: false,
      publicCount: 1,
      installed: true,
      installedCount: 2,
    });
    const partiallyInstalledPack = pack({
      id: "partially-installed",
      displayName: "Charlie Catalog Pack",
      fullyPublic: false,
      publicCount: 0,
      installed: false,
      installedCount: 1,
    });
    const availablePack = pack({
      id: "available-pack",
      displayName: "Delta Catalog Pack",
    });

    const component = await mount(
      <PacksTabTestWrapper
        mocks={[
          packsMock([
            fullyPublicPack,
            partiallyPublicPack,
            partiallyInstalledPack,
            availablePack,
          ]),
        ]}
      />
    );

    await expect(page.locator('[data-testid="pack-card"]')).toHaveCount(4, {
      timeout: 15000,
    });
    const cardFor = (title: string) =>
      page.locator('[data-testid="pack-card"]').filter({ hasText: title });

    await expect(
      cardFor("Alpha Catalog Pack").getByText("Fully public", { exact: true })
    ).toBeVisible();
    await expect(
      cardFor("Bravo Catalog Pack").getByText("Partially public", {
        exact: true,
      })
    ).toBeVisible();
    await expect(
      cardFor("Charlie Catalog Pack").getByText("Partially installed", {
        exact: true,
      })
    ).toBeVisible();
    await expect(
      cardFor("Delta Catalog Pack").getByText("Available", { exact: true })
    ).toBeVisible();

    await docScreenshot(page, "admin--authority-packs-tab--status-badges");
    await component.unmount();
  });
});

test.describe("Authority pack preflight without an import bridge", () => {
  test("shows the corpus-ZIP importer as unavailable when PacksTab has no import bridge", async ({
    mount,
    page,
  }) => {
    const installedPack = pack({
      installed: true,
      installedCount: 2,
      corpora: [
        corpus({
          corpusId: "Q29ycHVzVHlwZTox",
          installed: true,
          isPublic: true,
        }),
        corpus({
          slug: "puct-electric",
          title: "PUCT Electric Rules",
          installed: true,
        }),
      ],
    });
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[packsMock([installedPack]), preflightMock(installedPack)]}
      />
    );

    await page
      .locator(`[data-testid="pack-review-${installedPack.id}"]`)
      .click();
    const importAction = page.locator(
      '[data-testid="pack-import-corpus-texas-electric-law"]'
    );
    await expect(importAction).toBeVisible({ timeout: 15000 });
    await expect(importAction).toBeDisabled();
    await expect(importAction).toHaveAttribute(
      "title",
      "Corpus ZIP import is not connected in this view."
    );
    await expect(page.getByText("Public").first()).toBeVisible();

    await docScreenshot(page, "admin--pack-preflight-modal--import-unbridged");
    await component.unmount();
  });
});

test.describe("Authority pack preflight approval tones and summary badges", () => {
  test("falls back to the manifest name and covers neutral/review-only approval tones", async ({
    mount,
    page,
  }) => {
    const blankDisplayNamePack = pack({
      id: "blank-name-pack",
      name: "blank_name_pack",
      displayName: "",
      approvalStatus: "draft",
      corpora: [
        corpus({ approvalStatus: "needs_review" }),
        corpus({
          slug: "puct-electric",
          title: "PUCT Electric Rules",
          approvalStatus: "draft",
        }),
      ],
    });
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[
          packsMock([blankDisplayNamePack]),
          preflightMock(blankDisplayNamePack),
        ]}
      />
    );

    await page
      .locator(`[data-testid="pack-review-${blankDisplayNamePack.id}"]`)
      .click();
    await expect(
      page.locator('[data-testid="pack-preflight-title"]')
    ).toContainText("blank_name_pack", { timeout: 15000 });
    await expect(page.getByText("Draft").first()).toBeVisible();
    await expect(page.getByText("Needs Review")).toBeVisible();

    await docScreenshot(page, "admin--pack-preflight-modal--approval-tones");
    await component.unmount();
  });

  test("shows fully public, partially public, and partially installed status badges in the preflight", async ({
    mount,
    page,
  }) => {
    // See the "shows every catalog status badge" test above for why display
    // names avoid the badge label words themselves.
    const fullyPublicPack = pack({
      id: "fully-public-pack",
      displayName: "Echo Preflight Pack",
      fullyPublic: true,
      publicCount: 2,
      installed: true,
      installedCount: 2,
    });
    const partiallyPublicPack = pack({
      id: "partial-public-pack",
      displayName: "Foxtrot Preflight Pack",
      fullyPublic: false,
      publicCount: 1,
      installed: true,
      installedCount: 1,
    });
    const partiallyInstalledPack = pack({
      id: "partial-installed-pack",
      displayName: "Golf Preflight Pack",
      fullyPublic: false,
      publicCount: 0,
      installed: false,
      installedCount: 1,
    });

    const component = await mount(
      <PacksTabTestWrapper
        mocks={[
          packsMock([
            fullyPublicPack,
            partiallyPublicPack,
            partiallyInstalledPack,
          ]),
          preflightMock(fullyPublicPack),
          preflightMock(partiallyPublicPack),
          preflightMock(partiallyInstalledPack),
        ]}
      />
    );

    await page
      .locator(`[data-testid="pack-review-${fullyPublicPack.id}"]`)
      .click();
    await expect(
      page
        .locator('[data-testid="authority-pack-preflight"]')
        .getByText("Fully public", { exact: true })
    ).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).not.toBeVisible();

    await page
      .locator(`[data-testid="pack-review-${partiallyPublicPack.id}"]`)
      .click();
    await expect(
      page
        .locator('[data-testid="authority-pack-preflight"]')
        .getByText("Partially public", { exact: true })
    ).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Cancel" }).click();

    await page
      .locator(`[data-testid="pack-review-${partiallyInstalledPack.id}"]`)
      .click();
    await expect(
      page
        .locator('[data-testid="authority-pack-preflight"]')
        .getByText("Partially installed", { exact: true })
    ).toBeVisible({ timeout: 15000 });

    await docScreenshot(page, "admin--pack-preflight-modal--summary-badges");
    await component.unmount();
  });
});

test.describe("Authority pack preflight query states", () => {
  test("shows a loading spinner while the preflight query is in flight", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "slow-preflight-pack" });
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[packsMock([target]), { ...preflightMock(target), delay: 400 }]}
      />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    await expect(page.getByText("Validating authority pack…")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="pack-fingerprint"]')).toBeVisible({
      timeout: 15000,
    });

    await docScreenshot(page, "admin--pack-preflight-modal--loading");
    await component.unmount();
  });

  test("shows an error state when the fresh preflight query fails", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "broken-preflight-pack" });
    const errorMock = {
      request: {
        query: GET_AUTHORITY_PACK_PREFLIGHT,
        variables: { packId: target.id },
      },
      error: new Error("The preflight service is temporarily unavailable."),
    };
    const component = await mount(
      <PacksTabTestWrapper mocks={[packsMock([target]), errorMock]} />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    // As in the catalog-error test above, MockedProvider's `error:` field
    // routes through Apollo's own error-message decoder rather than
    // preserving the injected Error's message in this test environment, so
    // this only asserts the component's own error heading.
    await expect(page.getByText("Could not preflight pack")).toBeVisible({
      timeout: 15000,
    });
    await expect(page.locator('[data-testid="pack-fingerprint"]')).toHaveCount(
      0
    );
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toBeDisabled();

    await docScreenshot(page, "admin--pack-preflight-modal--preflight-error");
    await component.unmount();
  });

  test("shows a pack-unavailable message when the preflight query returns null", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "vanished-pack" });
    const nullMock = {
      request: {
        query: GET_AUTHORITY_PACK_PREFLIGHT,
        variables: { packId: target.id },
      },
      result: { data: { authorityPackPreflight: null } },
    };
    const component = await mount(
      <PacksTabTestWrapper mocks={[packsMock([target]), nullMock]} />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    await expect(page.getByText("Pack unavailable")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.getByText("The server did not return a preflight for this pack.")
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("Authority pack install outcomes", () => {
  test("keeps the modal open if the user tries to close it while installing", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "slow-install-pack" });
    const slowInstallMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: target.id,
          expectedFingerprint: target.fingerprint,
          publish: false,
        },
      },
      result: {
        data: {
          installAuthorityPack: {
            ok: true,
            message: "Authority pack installed privately.",
            result: { created: 2 },
            pack: target,
          },
        },
      },
      delay: 5000,
    };
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[packsMock([target]), preflightMock(target), slowInstallMock]}
      />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    const installButton = page.locator('[data-testid="pack-install-submit"]');
    await expect(installButton).toBeVisible({ timeout: 15000 });
    await installButton.click();
    await expect(installButton).toBeDisabled();

    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).toBeVisible();

    await docScreenshot(
      page,
      "admin--pack-preflight-modal--close-blocked-while-installing"
    );
    await component.unmount();
  });

  test("shows the server's rejection message when install returns ok:false", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "rejectable-pack" });
    const failMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: target.id,
          expectedFingerprint: target.fingerprint,
          publish: false,
        },
      },
      result: {
        data: {
          installAuthorityPack: {
            ok: false,
            message: "Corpus slug already exists on this server.",
            result: null,
            pack: null,
          },
        },
      },
    };
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[packsMock([target]), preflightMock(target), failMock]}
      />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="pack-install-submit"]').click();

    await expect(page.getByText("Installation failed")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.getByText("Corpus slug already exists on this server.").first()
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).toBeVisible();

    await docScreenshot(page, "admin--pack-preflight-modal--install-rejected");
    await component.unmount();
  });

  test("falls back to a generic message when install fails without a server message", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "silently-rejectable-pack" });
    const failMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: target.id,
          expectedFingerprint: target.fingerprint,
          publish: false,
        },
      },
      result: {
        data: {
          installAuthorityPack: {
            ok: false,
            message: null,
            result: null,
            pack: null,
          },
        },
      },
    };
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[packsMock([target]), preflightMock(target), failMock]}
      />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="pack-install-submit"]').click();

    await expect(
      page.getByText("Could not install authority pack.").first()
    ).toBeVisible({ timeout: 15000 });

    await component.unmount();
  });

  test("surfaces a thrown network error from the install mutation", async ({
    mount,
    page,
  }) => {
    const target = pack({ id: "network-error-pack" });
    const networkErrorMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: target.id,
          expectedFingerprint: target.fingerprint,
          publish: false,
        },
      },
      error: new Error("Network request failed."),
    };
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[packsMock([target]), preflightMock(target), networkErrorMock]}
      />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="pack-install-submit"]').click();

    // As above, the thrown Error's own message is replaced by Apollo's
    // error-message decoder in this test environment; what this test
    // verifies is the catch-block path itself: the rejected mutation is
    // caught, surfaced through the same "Installation failed" inline error
    // UI as a server-rejected (ok:false) install, and the modal stays open.
    await expect(page.getByText("Installation failed")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("installs and publishes, falling back to the default published message", async ({
    mount,
    page,
  }) => {
    const target = pack({
      id: "publishable-pack",
      approvalStatus: "approved",
      canPublish: true,
    });
    const installedTarget = {
      ...target,
      installed: true,
      installedCount: 2,
    };
    const publishMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: target.id,
          expectedFingerprint: target.fingerprint,
          publish: true,
        },
      },
      result: {
        data: {
          installAuthorityPack: {
            ok: true,
            message: null,
            result: { created: 2 },
            pack: installedTarget,
          },
        },
      },
    };
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[
          packsMock([target]),
          preflightMock(target),
          publishMock,
          packsMock([installedTarget]),
        ]}
      />
    );

    await page.locator(`[data-testid="pack-review-${target.id}"]`).click();
    const publishOption = page.locator('[data-testid="pack-publish-option"]');
    await expect(publishOption).toBeEnabled({ timeout: 15000 });
    await publishOption.check();
    await page.locator('[data-testid="pack-install-submit"]').click();

    await expect(
      page.getByText("Authority pack installed and published.")
    ).toBeVisible({ timeout: 15000 });

    await docScreenshot(
      page,
      "admin--pack-preflight-modal--install-and-publish"
    );
    await component.unmount();
  });

  test("falls back to default validation and install-success text when the server omits both messages", async ({
    mount,
    page,
  }) => {
    // The preflight modal's own validation-error fallback ("The manifest did
    // not pass server validation.") is a distinct string from PacksTab's card
    // fallback ("Manifest validation failed.") tested earlier, so it needs
    // its own null-validationError fixture. The catalog card itself must
    // stay valid (its Review button disables when `!pack.valid`) — this
    // mirrors AuthorityPacks.ct.tsx's "blocks installation when the fresh
    // preflight is invalid" test, where the catalog listing and the fresh
    // preflight fetch disagree.
    const catalogPack = pack({
      id: "invalid-no-message-pack",
      name: "invalid_no_message_pack",
    });
    const invalidPreflight = pack({
      ...catalogPack,
      valid: false,
      validationError: null,
      canInstall: false,
    });
    const privateTarget = pack({ id: "privately-installable-pack" });
    const privateInstallMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: privateTarget.id,
          expectedFingerprint: privateTarget.fingerprint,
          publish: false,
        },
      },
      result: {
        data: {
          installAuthorityPack: {
            ok: true,
            message: null,
            result: { created: 2 },
            pack: { ...privateTarget, installed: true, installedCount: 2 },
          },
        },
      },
    };
    const component = await mount(
      <PacksTabTestWrapper
        mocks={[
          packsMock([catalogPack, privateTarget]),
          preflightMock(invalidPreflight),
          preflightMock(privateTarget),
          privateInstallMock,
        ]}
      />
    );

    await page.locator(`[data-testid="pack-review-${catalogPack.id}"]`).click();
    await expect(
      page.getByText("The manifest did not pass server validation.")
    ).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: "Cancel" }).click();

    await page
      .locator(`[data-testid="pack-review-${privateTarget.id}"]`)
      .click();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toBeVisible({ timeout: 15000 });
    await page.locator('[data-testid="pack-install-submit"]').click();
    await expect(
      page.getByText("Authority pack installed privately.")
    ).toBeVisible({ timeout: 15000 });

    await component.unmount();
  });
});
