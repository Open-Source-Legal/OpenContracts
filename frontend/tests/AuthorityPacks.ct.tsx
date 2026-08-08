/**
 * Component tests for the Authority Console's server-discovered pack catalog.
 *
 * The flow deliberately has no path/URL/upload input: an administrator chooses
 * an opaque catalog id, reviews a fresh fingerprinted preflight, and installs
 * privately unless publication is both server-approved and explicitly chosen.
 */
import { test, expect } from "./utils/coverage";
import { AuthorityConsoleTestWrapper } from "./AuthorityConsoleTestWrapper";
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
    corpus({
      slug: "puct-electric",
      title: "PUCT Electric Rules",
    }),
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

const mountPacks = (mount: any, mocks: any[]) =>
  mount(
    <AuthorityConsoleTestWrapper
      mocks={mocks}
      superuser={true}
      initialPath="/admin/authority/packs"
    />
  );

test.describe("Authority packs", () => {
  test("lists only the server catalog and preserves existing console tabs", async ({
    mount,
    page,
  }) => {
    const invalidPack = pack({
      id: "invalid-pack",
      name: "invalid_pack",
      displayName: "Invalid Pack",
      description: "A broken fixture.",
      valid: false,
      validationError: "manifest.yaml: missing corpora",
      canInstall: false,
      totalCorpora: 0,
      corpora: [],
      sourceHosts: [],
    });
    const component = await mountPacks(mount, [
      packsMock([pack(), invalidPack]),
    ]);

    await expect(
      page.locator('[data-testid="authority-packs-tab"]')
    ).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="pack-card"]')).toHaveCount(2);
    await expect(page.getByText("Texas Electric Law").first()).toBeVisible();
    await expect(
      page.getByText("manifest.yaml: missing corpora")
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="packs-server-catalog-note"]')
    ).toContainText("cannot upload pack code");

    // The pack catalog extends the existing console; it does not replace or
    // reroute any of its established sections.
    await expect(
      page.locator('[data-testid="authority-tab-registry"]')
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="authority-tab-scrapers"]')
    ).toBeVisible();

    // There is deliberately no browser-controlled pack source input.
    await expect(page.locator('input[type="file"]')).toHaveCount(0);
    await expect(page.getByPlaceholder(/path|url/i)).toHaveCount(0);

    await component.unmount();
  });

  test("shows a structured preflight and installs privately by default", async ({
    mount,
    page,
  }) => {
    const available = pack();
    const installed = pack({
      installed: true,
      installedCount: 2,
      corpora: [
        corpus({
          corpusId: "Q29ycHVzVHlwZTox",
          installed: true,
        }),
        corpus({
          corpusId: "Q29ycHVzVHlwZToy",
          slug: "puct-electric",
          title: "PUCT Electric Rules",
          installed: true,
        }),
      ],
    });
    const installMock = {
      request: {
        query: INSTALL_AUTHORITY_PACK,
        variables: {
          packId: available.id,
          expectedFingerprint: available.fingerprint,
          publish: false,
        },
      },
      result: {
        data: {
          installAuthorityPack: {
            ok: true,
            message: "Authority pack installed privately.",
            result: { created: 2 },
            pack: installed,
          },
        },
      },
      delay: 600,
    };

    const component = await mountPacks(mount, [
      packsMock([available]),
      preflightMock(available),
      installMock,
      packsMock([installed]),
    ]);

    await page.locator(`[data-testid="pack-review-${available.id}"]`).click();
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="pack-corpus-row"]')).toHaveCount(
      2
    );
    await expect(page.getByText("statutes.capitol.texas.gov")).toBeVisible();
    await expect(page.locator('[data-testid="pack-fingerprint"]')).toHaveText(
      available.fingerprint
    );
    await expect(page.getByText("Publication unavailable")).toBeVisible();

    const publishOption = page.locator('[data-testid="pack-publish-option"]');
    await expect(publishOption).not.toBeChecked();
    await expect(publishOption).toBeDisabled();

    const installButton = page.locator('[data-testid="pack-install-submit"]');
    await expect(installButton).toContainText("Install privately");
    await installButton.click();
    await expect(installButton).toBeDisabled();

    await expect(
      page.getByText("Authority pack installed privately.")
    ).toBeVisible({ timeout: 15000 });
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).not.toBeVisible();
    await expect(
      page.locator('[data-testid="pack-card"]').getByText("Installed privately")
    ).toBeVisible();

    await component.unmount();
  });

  test("requires an explicit choice before publishing an approved pack", async ({
    mount,
    page,
  }) => {
    const approved = pack({
      id: "approved-pack",
      name: "approved_pack",
      displayName: "Approved Pack",
      approvalStatus: "approved",
      canPublish: true,
      corpora: [
        corpus({
          slug: "approved-corpus",
          title: "Approved Corpus",
          approvalStatus: "approved",
        }),
      ],
      totalCorpora: 1,
      sourceHosts: [],
    });
    const component = await mountPacks(mount, [
      packsMock([approved]),
      preflightMock(approved),
    ]);

    await page.locator(`[data-testid="pack-review-${approved.id}"]`).click();
    const publishOption = page.locator('[data-testid="pack-publish-option"]');
    await expect(publishOption).toBeEnabled({ timeout: 15000 });
    await expect(publishOption).not.toBeChecked();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toContainText("Install privately");

    await publishOption.check();
    await expect(page.getByText("Public access is explicit")).toBeVisible();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toContainText("Install and publish");
    await expect(page.getByText(/anonymously readable/)).toBeVisible();

    await component.unmount();
  });

  test("blocks installation when the fresh preflight is invalid", async ({
    mount,
    page,
  }) => {
    const catalogPack = pack({
      id: "changed-pack",
      name: "changed_pack",
      displayName: "Changed Pack",
    });
    const invalidPreflight = pack({
      ...catalogPack,
      valid: false,
      validationError: "Corpus slug collides with an unrelated corpus.",
      canInstall: false,
      canPublish: false,
    });
    const component = await mountPacks(mount, [
      packsMock([catalogPack]),
      preflightMock(invalidPreflight),
    ]);

    await page.locator(`[data-testid="pack-review-${catalogPack.id}"]`).click();
    await expect(page.getByText("Pack failed validation")).toBeVisible({
      timeout: 15000,
    });
    await expect(
      page.getByText("Corpus slug collides with an unrelated corpus.")
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toBeDisabled();
    await expect(
      page.locator('[data-testid="pack-install-submit"]')
    ).toContainText("Nothing to install");

    await component.unmount();
  });

  test("opens the existing ZIP importer against an installed corpus", async ({
    mount,
    page,
  }) => {
    const installed = pack({
      installed: true,
      installedCount: 2,
      corpora: [
        corpus({
          corpusId: "Q29ycHVzVHlwZTox",
          installed: true,
        }),
        corpus({
          corpusId: null,
          slug: "puct-electric",
          title: "PUCT Electric Rules",
          installed: true,
        }),
      ],
    });
    const component = await mountPacks(mount, [
      packsMock([installed]),
      preflightMock(installed),
    ]);

    await page.locator(`[data-testid="pack-review-${installed.id}"]`).click();
    const importAction = page.locator(
      '[data-testid="pack-import-corpus-texas-electric-law"]'
    );
    await expect(importAction).toContainText("Import corpus ZIP", {
      timeout: 15000,
    });
    await expect(importAction).toBeEnabled();
    await expect(page.getByText("Corpus ID unavailable")).toBeVisible();

    await importAction.click();
    await expect(
      page.locator('[data-testid="authority-pack-preflight"]')
    ).not.toBeVisible();
    await expect(page.getByText("Sideload Corpus")).toBeVisible();
    await expect(
      page.getByText("Import into Texas Electric Law")
    ).toBeVisible();

    await component.unmount();
  });
});
