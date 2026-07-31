/**
 * Full-stack authority pack + sideload workflow.
 *
 * The standalone corpus builders write pack-local `imports/index.json` files.
 * Set E2E_RUN_AUTHORITY_IMPORTS=true after running those builders. This spec:
 *
 *  1. logs in through the real password form,
 *  2. installs all four packs through fresh GUI preflights,
 *  3. uploads all ten generated corpus exports through targeted GUI import,
 *  4. waits for every import batch to report DONE in the admin monitor,
 *  5. rejects any collector report, manifest, imported document, or parsed
 *     text layer that represents the former synthetic link-only artifacts,
 *  6. proves canonical-key/path reconciliation and full publisher-content
 *     ingestion for every document via read-only GraphQL/file inspection,
 *  7. proves pending baseline edges stay out of the production graph, and
 *  8. opens one real document per corpus and checks a publisher-text sentinel.
 *
 * No manage.py command, direct model write, mocked operation, or API mutation
 * is used to prepare or drive the workflow.
 */

import { test, expect } from "./fixtures";
import { TEST_USER } from "./helpers";
import {
  AuthorityPackInstallObservation,
  CanonicalCorpusObservation,
  StartedCorpusImport,
  expectCanonicalCorpusState,
  expectImportedContentViaUI,
  expectProvisionalRelationshipsExcludedFromGovernanceGraph,
  installAuthorityPackViaUI,
  loadAuthorityPackImportCases,
  loadProvisionalAuthorityRelationships,
  loginViaUIWithToken,
  uploadAuthorityCorpusExportViaUI,
  waitForAuthorityCorpusDocumentsCompleted,
  waitForCorpusImportsDoneViaUI,
} from "./authority-pack-helpers";

const RUN_AUTHORITY_IMPORTS = process.env.E2E_RUN_AUTHORITY_IMPORTS === "true";
const importCases = RUN_AUTHORITY_IMPORTS ? loadAuthorityPackImportCases() : [];

test.describe("Authority pack corpus sideload", () => {
  test.skip(
    !RUN_AUTHORITY_IMPORTS,
    "Run the standalone corpus builders, then set " +
      "E2E_RUN_AUTHORITY_IMPORTS=true. Pack-local imports/index.json files " +
      "are discovered automatically."
  );

  test.setTimeout(120 * 60 * 1000);

  test("installs four packs and hydrates all ten corpora through the GUI", async ({
    page,
  }) => {
    const packNames = [...new Set(importCases.map((entry) => entry.packName))];
    expect(
      packNames,
      "The generated manifest set must cover exactly four authority packs"
    ).toHaveLength(4);
    expect(
      importCases,
      "The generated manifest set must cover exactly ten authority corpora"
    ).toHaveLength(10);
    const provisionalRelationships =
      loadProvisionalAuthorityRelationships(packNames);
    expect(
      provisionalRelationships,
      "The four pack manifests must declare the eleven pending baseline edges"
    ).toHaveLength(11);

    let token = "";
    await test.step("log in as the migrated administrator", async () => {
      token = await loginViaUIWithToken(
        page,
        TEST_USER.username,
        TEST_USER.password
      );
    });

    const installObservations: AuthorityPackInstallObservation[] = [];
    for (const packName of packNames) {
      await test.step(`install pack: ${packName}`, async () => {
        installObservations.push(
          await installAuthorityPackViaUI(page, packName)
        );
      });
    }

    await test.step("verify all declared baseline edges were reconciled", async () => {
      expect(installObservations).toHaveLength(packNames.length);
      let reconciledTotal = 0;
      for (const observation of installObservations) {
        const declaredCount = provisionalRelationships.filter(
          (relationship) => relationship.packName === observation.packName
        ).length;
        const reconciled =
          observation.relationships.created +
          observation.relationships.updated +
          observation.relationships.unchanged;
        expect(
          reconciled,
          `${observation.packName} install must account for every declared baseline edge`
        ).toBe(declaredCount);
        expect(
          observation.relationships.preservedManual +
            observation.relationships.preservedBaseline +
            observation.relationships.skippedForeign +
            observation.relationships.deleted,
          `${observation.packName} must not skip, preserve a conflict, or delete a declared baseline edge`
        ).toBe(0);
        reconciledTotal += reconciled;
      }
      expect(reconciledTotal).toBe(11);
    });

    const startedImports: StartedCorpusImport[] = [];
    for (const importCase of importCases) {
      await test.step(`upload ${importCase.corpusSlug}`, async () => {
        startedImports.push(
          await uploadAuthorityCorpusExportViaUI(page, importCase)
        );
      });
    }

    await test.step("wait for all import batches to finish", async () => {
      await waitForCorpusImportsDoneViaUI(page, importCases);
      await waitForAuthorityCorpusDocumentsCompleted(
        page,
        token,
        startedImports
      );
    });

    const canonicalObservations: CanonicalCorpusObservation[] = [];
    for (const startedImport of startedImports) {
      await test.step(`verify canonical identity: ${startedImport.testCase.corpusSlug}`, async () => {
        canonicalObservations.push(
          await expectCanonicalCorpusState(page, token, startedImport)
        );
      });
    }

    await test.step("audit imported authority relationships and their legal gate", async () => {
      const expectedProviderRelationships = importCases.flatMap(
        (importCase) => importCase.expectedProviderRelationships
      );
      expect(
        expectedProviderRelationships.length,
        "The generated manifests must declare the provider graph extracted from publisher records"
      ).toBeGreaterThan(0);

      // A provider may independently corroborate a baseline declaration. The
      // persistence model intentionally reconciles that shared edge identity,
      // so audit the deduplicated graph contract rather than treating
      // corroboration as a duplicate-edge failure.
      const relationshipsByIdentity = new Map(
        [...provisionalRelationships, ...expectedProviderRelationships].map(
          (relationship) => [
            `${relationship.sourceKey}\u0000${relationship.relationshipType}\u0000${relationship.targetKey}`,
            relationship,
          ]
        )
      );
      const allRelationships = [...relationshipsByIdentity.values()];

      const importedCanonicalKeys = new Set(
        canonicalObservations.flatMap((observation) =>
          Object.values(observation.canonicalKeyByDocumentId)
        )
      );
      for (const relationship of provisionalRelationships) {
        expect(
          importedCanonicalKeys.has(relationship.sourceKey),
          `Baseline relationship source is missing from the ten imported corpora: ${relationship.sourceKey}`
        ).toBe(true);
        expect(
          importedCanonicalKeys.has(relationship.targetKey),
          `Baseline relationship target is missing from the ten imported corpora: ${relationship.targetKey}`
        ).toBe(true);
      }
      // NOTE: these assertions check that each declared edge's ENDPOINTS were
      // imported as canonical keys. They do NOT prove an AuthorityRelationship
      // row was created for the edge, and cannot: provider edges are
      // `verified: false`, so the governance graph excludes them by design, and
      // no GraphQL surface exposes the relationship table. A corpus whose
      // canonical-key prefix is unbound imports every document and promotes
      // zero edges, and every assertion in this block still passes — that is
      // exactly how 154 declared edges went missing on the reference
      // deployment. The guards that do catch it are backend-side:
      // test_grid_dossier_authority_pack_data.py::
      //   test_every_declared_prefix_is_bound_to_exactly_one_pack_corpus
      // test_authority_targeted_import.py::
      //   test_corpus_with_no_bound_prefix_silently_skips_reconciliation
      for (const relationship of allRelationships) {
        expect(
          importedCanonicalKeys.has(relationship.sourceKey),
          `Relationship source is missing from the ten imported corpora: ${relationship.sourceKey}`
        ).toBe(true);
        if (relationship.relationshipType === "FILED_IN") {
          expect(
            importedCanonicalKeys.has(relationship.targetKey),
            `Filed-in relationship target is missing from the ten imported corpora: ${relationship.targetKey}`
          ).toBe(true);
        }
      }

      await expectProvisionalRelationshipsExcludedFromGovernanceGraph(
        page,
        token,
        canonicalObservations,
        allRelationships
      );
    });

    for (const importCase of importCases) {
      await test.step(`verify rendered content: ${importCase.corpusSlug}`, async () => {
        const corpusObservation = canonicalObservations.find(
          (observation) =>
            observation.packName === importCase.packName &&
            observation.corpusSlug === importCase.corpusSlug
        );
        expect(
          corpusObservation,
          `No canonical observation available for ${importCase.packName}/${importCase.corpusSlug}`
        ).toBeDefined();
        if (!corpusObservation) {
          throw new Error(
            `No canonical observation available for ${importCase.packName}/${importCase.corpusSlug}`
          );
        }
        await expectImportedContentViaUI(page, importCase, corpusObservation);
      });
    }
  });
});
