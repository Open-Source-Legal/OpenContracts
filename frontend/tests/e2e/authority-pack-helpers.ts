/**
 * Real-browser helpers for the authority-pack sideload workflow.
 *
 * State-changing operations deliberately go through production UI controls:
 * pack installation uses the preflight modal and corpus hydration uses the
 * targeted ImportCorpusModal. Read-only GraphQL inspection is used only after
 * the UI workflow completes, to prove canonical identity/path invariants that
 * are not all rendered in the current document cards.
 */

import fs from "fs";
import path from "path";
import { Page, expect } from "@playwright/test";
import { load as loadYaml } from "js-yaml";

import { loginViaUI, spaNavigate } from "./helpers";

const REPO_ROOT = path.resolve(__dirname, "../../..");
const PACK_ROOT = path.join(
  REPO_ROOT,
  "opencontractserver",
  "enrichment",
  "data",
  "authority_packs"
);
const DJANGO_URL =
  process.env.E2E_DJANGO_URL ||
  process.env.REACT_APP_API_ROOT_URL ||
  "http://127.0.0.1:8000";
const SYNTHETIC_LINK_ONLY_MARKERS = [
  "Link-only authority source",
  "Full publisher content was not fetched",
] as const;
const SHA256_HEX_RE = /^[0-9a-f]{64}$/;

export interface AuthorityPackImportCase {
  packName: string;
  corpusSlug: string;
  corpusTitle: string;
  exportZipPath: string;
  expectedDocumentTitle: string;
  expectedContentText: string;
  expectedCanonicalKeys: string[];
  expectedDocumentCount: number;
  expectedProviderRelationships: ProvisionalAuthorityRelationship[];
  /** Absolute path of the index that declared this case (diagnostics only). */
  manifestPath: string;
}

export interface ProvisionalAuthorityRelationship {
  packName: string;
  sourceKey: string;
  relationshipType: string;
  targetKey: string;
}

export interface RelationshipReconciliationCounts {
  created: number;
  updated: number;
  unchanged: number;
  preservedManual: number;
  preservedBaseline: number;
  skippedForeign: number;
  deleted: number;
}

export interface AuthorityPackInstallObservation {
  packName: string;
  relationships: RelationshipReconciliationCounts;
}

interface RawAuthorityPackImportCase {
  packName?: unknown;
  corpusSlug?: unknown;
  corpusTitle?: unknown;
  exportZipPath?: unknown;
  expectedDocumentTitle?: unknown;
  expectedContentText?: unknown;
  expectedCanonicalKeys?: unknown;
  expectedDocumentCount?: unknown;
  expectedProviderRelationships?: unknown;
}

interface RawExpectedProviderRelationship {
  sourceKey?: unknown;
  relationshipType?: unknown;
  targetKey?: unknown;
}

interface RawAuthorityPackImportManifest {
  cases?: unknown;
}

interface RawCollectionReport {
  pack_name?: unknown;
  fetched?: unknown;
  linked?: unknown;
  rights_approved?: unknown;
  decisions?: unknown;
  artifact_warnings?: unknown;
  errors?: unknown;
}

interface RawCollectionDecision {
  ingestion_mode?: unknown;
  verdict?: unknown;
}

interface RawAuthorityPackManifest {
  name?: unknown;
  relationships?: unknown;
}

interface RawRelationshipManifest {
  relationships?: unknown;
}

interface RawRelationshipDeclaration {
  source_key?: unknown;
  relationship_type?: unknown;
  target_key?: unknown;
  verified?: unknown;
  metadata?: unknown;
}

function requireNonEmptyString(
  raw: unknown,
  field: string,
  manifestPath: string
): string {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new Error(
      `${manifestPath}: field "${field}" must be a non-empty string`
    );
  }
  return raw.trim();
}

function resolveManifestPath(candidate: string): string {
  return path.isAbsolute(candidate)
    ? path.normalize(candidate)
    : path.resolve(REPO_ROOT, candidate);
}

function discoverManifestPaths(): string[] {
  const configured =
    process.env.E2E_AUTHORITY_IMPORT_MANIFESTS ||
    process.env.E2E_AUTHORITY_IMPORT_MANIFEST;
  if (configured) {
    return configured
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map(resolveManifestPath);
  }

  if (!fs.existsSync(PACK_ROOT)) return [];
  return fs
    .readdirSync(PACK_ROOT, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(PACK_ROOT, entry.name, "imports", "index.json"))
    .filter((candidate) => fs.existsSync(candidate))
    .sort();
}

function readManifest(manifestPath: string): AuthorityPackImportCase[] {
  if (!fs.existsSync(manifestPath)) {
    throw new Error(
      `Authority import manifest does not exist: ${manifestPath}`
    );
  }

  let raw: RawAuthorityPackImportManifest;
  try {
    raw = JSON.parse(
      fs.readFileSync(manifestPath, "utf-8")
    ) as RawAuthorityPackImportManifest;
  } catch (error) {
    throw new Error(
      `Could not parse authority import manifest ${manifestPath}: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }

  if (!Array.isArray(raw.cases) || raw.cases.length === 0) {
    throw new Error(`${manifestPath}: "cases" must be a non-empty array`);
  }

  const manifestDir = path.dirname(manifestPath);
  return raw.cases.map((value, index) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${manifestPath}: cases[${index}] must be an object`);
    }
    const entry = value as RawAuthorityPackImportCase;
    const exportZipValue = requireNonEmptyString(
      entry.exportZipPath,
      "exportZipPath",
      manifestPath
    );
    const exportZipPath = path.isAbsolute(exportZipValue)
      ? path.normalize(exportZipValue)
      : path.resolve(manifestDir, exportZipValue);
    if (!fs.existsSync(exportZipPath)) {
      throw new Error(
        `${manifestPath}: corpus export ZIP does not exist: ${exportZipPath}`
      );
    }
    if (path.extname(exportZipPath).toLowerCase() !== ".zip") {
      throw new Error(
        `${manifestPath}: exportZipPath must name a ZIP: ${exportZipPath}`
      );
    }

    if (
      !Array.isArray(entry.expectedCanonicalKeys) ||
      entry.expectedCanonicalKeys.length === 0 ||
      entry.expectedCanonicalKeys.some(
        (key) => typeof key !== "string" || key.trim() === ""
      )
    ) {
      throw new Error(
        `${manifestPath}: cases[${index}].expectedCanonicalKeys must be a non-empty string array`
      );
    }
    const expectedCanonicalKeys = entry.expectedCanonicalKeys.map((key) =>
      (key as string).trim()
    );
    if (new Set(expectedCanonicalKeys).size !== expectedCanonicalKeys.length) {
      throw new Error(
        `${manifestPath}: cases[${index}].expectedCanonicalKeys contains duplicates`
      );
    }

    if (
      typeof entry.expectedDocumentCount !== "number" ||
      !Number.isInteger(entry.expectedDocumentCount) ||
      entry.expectedDocumentCount <= 0
    ) {
      throw new Error(
        `${manifestPath}: cases[${index}].expectedDocumentCount must be a positive integer`
      );
    }
    if (entry.expectedDocumentCount !== expectedCanonicalKeys.length) {
      throw new Error(
        `${manifestPath}: cases[${index}] expectedDocumentCount (${entry.expectedDocumentCount}) ` +
          `must equal expectedCanonicalKeys.length (${expectedCanonicalKeys.length})`
      );
    }

    if (!Array.isArray(entry.expectedProviderRelationships)) {
      throw new Error(
        `${manifestPath}: cases[${index}].expectedProviderRelationships must be an array`
      );
    }
    const packName = requireNonEmptyString(
      entry.packName,
      "packName",
      manifestPath
    );
    const expectedProviderRelationships =
      entry.expectedProviderRelationships.map((value, relationshipIndex) => {
        if (!value || typeof value !== "object" || Array.isArray(value)) {
          throw new Error(
            `${manifestPath}: cases[${index}].expectedProviderRelationships[${relationshipIndex}] must be an object`
          );
        }
        const relationship = value as RawExpectedProviderRelationship;
        const sourceKey = requireNonEmptyString(
          relationship.sourceKey,
          "sourceKey",
          manifestPath
        );
        if (!expectedCanonicalKeys.includes(sourceKey)) {
          throw new Error(
            `${manifestPath}: expected provider relationship source ${sourceKey} is not a document in cases[${index}]`
          );
        }
        return {
          packName,
          sourceKey,
          relationshipType: requireNonEmptyString(
            relationship.relationshipType,
            "relationshipType",
            manifestPath
          ),
          targetKey: requireNonEmptyString(
            relationship.targetKey,
            "targetKey",
            manifestPath
          ),
        };
      });
    const relationshipIdentities = expectedProviderRelationships.map(
      (relationship) =>
        `${relationship.sourceKey}\u0000${relationship.relationshipType}\u0000${relationship.targetKey}`
    );
    if (
      new Set(relationshipIdentities).size !== relationshipIdentities.length
    ) {
      throw new Error(
        `${manifestPath}: cases[${index}].expectedProviderRelationships contains duplicates`
      );
    }

    const expectedContentText = requireNonEmptyString(
      entry.expectedContentText,
      "expectedContentText",
      manifestPath
    );
    for (const marker of SYNTHETIC_LINK_ONLY_MARKERS) {
      if (expectedContentText.includes(marker)) {
        throw new Error(
          `${manifestPath}: cases[${index}].expectedContentText contains the ` +
            `synthetic link-only marker ${JSON.stringify(marker)}; rebuild ` +
            "the archive with fetched publisher content"
        );
      }
    }

    return {
      packName,
      corpusSlug: requireNonEmptyString(
        entry.corpusSlug,
        "corpusSlug",
        manifestPath
      ),
      corpusTitle: requireNonEmptyString(
        entry.corpusTitle,
        "corpusTitle",
        manifestPath
      ),
      exportZipPath,
      expectedDocumentTitle: requireNonEmptyString(
        entry.expectedDocumentTitle,
        "expectedDocumentTitle",
        manifestPath
      ),
      expectedContentText,
      expectedCanonicalKeys,
      expectedDocumentCount: entry.expectedDocumentCount,
      expectedProviderRelationships,
      manifestPath,
    };
  });
}

function requireNonNegativeReportInteger(
  raw: unknown,
  field: string,
  reportPath: string
): number {
  if (typeof raw !== "number" || !Number.isInteger(raw) || raw < 0) {
    throw new Error(
      `${reportPath}: field "${field}" must be a non-negative integer`
    );
  }
  return raw;
}

/**
 * Prove that the collector actually fetched every document represented by the
 * archive manifests. This deliberately rejects the former link-only build
 * even before the first state-changing browser action.
 */
function assertFullContentCollectionReports(
  cases: AuthorityPackImportCase[]
): void {
  const casesByPack = new Map<string, AuthorityPackImportCase[]>();
  for (const testCase of cases) {
    const packCases = casesByPack.get(testCase.packName) || [];
    packCases.push(testCase);
    casesByPack.set(testCase.packName, packCases);
  }

  for (const [packName, packCases] of casesByPack) {
    const { packDir } = findPackManifest(packName);
    const reportPath = path.join(packDir, "imports", "scrape-report.json");
    if (!fs.existsSync(reportPath)) {
      throw new Error(
        `Full-content collection report does not exist: ${reportPath}`
      );
    }

    let report: RawCollectionReport;
    try {
      report = JSON.parse(
        fs.readFileSync(reportPath, "utf-8")
      ) as RawCollectionReport;
    } catch (error) {
      throw new Error(
        `Could not parse collection report ${reportPath}: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
    }

    if (report.pack_name !== packName) {
      throw new Error(
        `${reportPath}: pack_name ${JSON.stringify(
          report.pack_name
        )} does not match ${JSON.stringify(packName)}`
      );
    }
    if (report.rights_approved !== true) {
      throw new Error(
        `${reportPath}: rights_approved must be true for this complete ` +
          "publisher-content acceptance run"
      );
    }
    if (!Array.isArray(report.errors) || report.errors.length !== 0) {
      throw new Error(
        `${reportPath}: collection errors must be an empty array`
      );
    }
    if (
      !Array.isArray(report.artifact_warnings) ||
      report.artifact_warnings.length !== 0
    ) {
      throw new Error(
        `${reportPath}: artifact_warnings must be an empty array`
      );
    }

    const linked = requireNonNegativeReportInteger(
      report.linked,
      "linked",
      reportPath
    );
    if (linked !== 0) {
      throw new Error(
        `${reportPath}: linked must be 0 for a full-content acceptance run; got ${linked}`
      );
    }

    const expectedDocuments = packCases.reduce(
      (total, testCase) => total + testCase.expectedDocumentCount,
      0
    );
    const fetched = requireNonNegativeReportInteger(
      report.fetched,
      "fetched",
      reportPath
    );
    if (fetched !== expectedDocuments) {
      throw new Error(
        `${reportPath}: fetched ${fetched} documents, but the archive ` +
          `manifests declare ${expectedDocuments}`
      );
    }

    if (!Array.isArray(report.decisions) || report.decisions.length === 0) {
      throw new Error(`${reportPath}: decisions must be a non-empty array`);
    }
    report.decisions.forEach((value, index) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error(`${reportPath}: decisions[${index}] must be an object`);
      }
      const decision = value as RawCollectionDecision;
      if (
        decision.ingestion_mode !== "full_content" ||
        decision.verdict !== "ok"
      ) {
        throw new Error(
          `${reportPath}: decisions[${index}] is not an approved ` +
            `full-content fetch: ${JSON.stringify(decision)}`
        );
      }
    });
  }
}

/**
 * Load the scraper-produced browser contract.
 *
 * Callers may set E2E_AUTHORITY_IMPORT_MANIFESTS to a comma-separated list of
 * index files. Without it, every pack-local `imports/index.json` is discovered.
 */
export function loadAuthorityPackImportCases(): AuthorityPackImportCase[] {
  const manifestPaths = discoverManifestPaths();
  if (manifestPaths.length === 0) {
    throw new Error(
      "No authority import manifests found. Run the standalone corpus builders " +
        "first or set E2E_AUTHORITY_IMPORT_MANIFESTS."
    );
  }

  const cases = manifestPaths.flatMap(readManifest);
  const identities = new Set<string>();
  const canonicalKeys = new Set<string>();
  const providerRelationshipIdentities = new Set<string>();
  for (const testCase of cases) {
    const identity = `${testCase.packName}/${testCase.corpusSlug}`;
    if (identities.has(identity)) {
      throw new Error(`Duplicate authority import case: ${identity}`);
    }
    identities.add(identity);
    for (const canonicalKey of testCase.expectedCanonicalKeys) {
      if (canonicalKeys.has(canonicalKey)) {
        throw new Error(
          `Duplicate canonical key across authority import cases: ${canonicalKey}`
        );
      }
      canonicalKeys.add(canonicalKey);
    }
    for (const relationship of testCase.expectedProviderRelationships) {
      const relationshipIdentity =
        `${relationship.sourceKey}\u0000` +
        `${relationship.relationshipType}\u0000${relationship.targetKey}`;
      if (providerRelationshipIdentities.has(relationshipIdentity)) {
        throw new Error(
          "Duplicate provider relationship across authority import cases: " +
            `${relationship.sourceKey} ${relationship.relationshipType} ` +
            relationship.targetKey
        );
      }
      providerRelationshipIdentities.add(relationshipIdentity);
    }
  }
  assertFullContentCollectionReports(cases);
  return cases.sort((a, b) =>
    `${a.packName}/${a.corpusSlug}`.localeCompare(
      `${b.packName}/${b.corpusSlug}`
    )
  );
}

function readYamlObject(
  filePath: string,
  description: string
): Record<string, unknown> {
  if (!fs.existsSync(filePath)) {
    throw new Error(`${description} does not exist: ${filePath}`);
  }
  let parsed: unknown;
  try {
    parsed = loadYaml(fs.readFileSync(filePath, "utf-8"));
  } catch (error) {
    throw new Error(
      `Could not parse ${description} ${filePath}: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${description} must contain a YAML object: ${filePath}`);
  }
  return parsed as Record<string, unknown>;
}

function findPackManifest(packName: string): {
  packDir: string;
  manifest: RawAuthorityPackManifest;
} {
  const matches = fs
    .readdirSync(PACK_ROOT, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(PACK_ROOT, entry.name))
    .map((packDir) => ({
      packDir,
      manifestPath: path.join(packDir, "pack.yaml"),
    }))
    .filter(({ manifestPath }) => fs.existsSync(manifestPath))
    .map(({ packDir, manifestPath }) => ({
      packDir,
      manifest: readYamlObject(
        manifestPath,
        "authority pack manifest"
      ) as RawAuthorityPackManifest,
    }))
    .filter(({ manifest }) => manifest.name === packName);

  if (matches.length !== 1) {
    throw new Error(
      `Expected exactly one pack.yaml with name "${packName}", found ${matches.length}`
    );
  }
  return matches[0];
}

/**
 * Load the packs' baseline relationship declarations and prove they are still
 * pending legal review. The same source files drive the backend installer, so
 * this avoids maintaining a second relationship fixture in the browser suite.
 */
export function loadProvisionalAuthorityRelationships(
  packNames: string[]
): ProvisionalAuthorityRelationship[] {
  const declarations: ProvisionalAuthorityRelationship[] = [];
  const identities = new Set<string>();

  for (const packName of packNames) {
    const { packDir, manifest } = findPackManifest(packName);
    const relationshipsValue = requireNonEmptyString(
      manifest.relationships,
      "relationships",
      path.join(packDir, "pack.yaml")
    );
    const relationshipsPath = path.resolve(packDir, relationshipsValue);
    const raw = readYamlObject(
      relationshipsPath,
      "authority relationship manifest"
    ) as RawRelationshipManifest;
    if (!Array.isArray(raw.relationships) || raw.relationships.length === 0) {
      throw new Error(
        `${relationshipsPath}: "relationships" must be a non-empty array`
      );
    }

    raw.relationships.forEach((value, index) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error(
          `${relationshipsPath}: relationships[${index}] must be an object`
        );
      }
      const entry = value as RawRelationshipDeclaration;
      if (entry.verified !== false) {
        throw new Error(
          `${relationshipsPath}: relationships[${index}] must remain verified=false until legal review`
        );
      }
      if (
        !entry.metadata ||
        typeof entry.metadata !== "object" ||
        Array.isArray(entry.metadata) ||
        (entry.metadata as Record<string, unknown>).review_status !==
          "pending_legal_review"
      ) {
        throw new Error(
          `${relationshipsPath}: relationships[${index}] must have metadata.review_status=pending_legal_review`
        );
      }

      const declaration = {
        packName,
        sourceKey: requireNonEmptyString(
          entry.source_key,
          "source_key",
          relationshipsPath
        ),
        relationshipType: requireNonEmptyString(
          entry.relationship_type,
          "relationship_type",
          relationshipsPath
        ),
        targetKey: requireNonEmptyString(
          entry.target_key,
          "target_key",
          relationshipsPath
        ),
      };
      const identity = `${declaration.sourceKey}\u0000${declaration.relationshipType}\u0000${declaration.targetKey}`;
      if (identities.has(identity)) {
        throw new Error(
          `Duplicate baseline relationship declaration: ${declaration.sourceKey} ${declaration.relationshipType} ${declaration.targetKey}`
        );
      }
      identities.add(identity);
      declarations.push(declaration);
    });
  }

  return declarations.sort((a, b) =>
    `${a.packName}/${a.sourceKey}/${a.relationshipType}/${a.targetKey}`.localeCompare(
      `${b.packName}/${b.sourceKey}/${b.relationshipType}/${b.targetKey}`
    )
  );
}

export async function loginViaUIWithToken(
  page: Page,
  username: string,
  password: string
): Promise<string> {
  const loginResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/graphql/") &&
      response.request().method() === "POST" &&
      (response.request().postData() || "").includes("tokenAuth"),
    { timeout: 30_000 }
  );

  await loginViaUI(page, username, password);
  const response = await loginResponsePromise;
  const payload = (await response.json()) as {
    data?: { tokenAuth?: { token?: unknown } };
    errors?: Array<{ message?: string }>;
  };
  const token = payload.data?.tokenAuth?.token;
  if (typeof token !== "string" || token === "") {
    throw new Error(
      `UI login did not return a JWT: ${
        payload.errors?.map((error) => error.message).join("; ") ||
        "missing tokenAuth.token"
      }`
    );
  }
  return token;
}

function packCard(page: Page, packName: string) {
  return page.getByTestId("pack-card").filter({ hasText: packName }).first();
}

function requireNonNegativeInteger(raw: unknown, field: string): number {
  if (typeof raw !== "number" || !Number.isInteger(raw) || raw < 0) {
    throw new Error(
      `installAuthorityPack result.relationships.${field} must be a non-negative integer; got ${JSON.stringify(
        raw
      )}`
    );
  }
  return raw;
}

function isInstallAuthorityPackRequest(
  request: import("@playwright/test").Request
): boolean {
  if (
    !new URL(request.url()).pathname.endsWith("/graphql/") ||
    request.method() !== "POST"
  ) {
    return false;
  }
  return (request.postData() || "").includes("InstallAuthorityPack");
}

async function openPackPreflight(page: Page, packName: string): Promise<void> {
  await spaNavigate(page, "/admin/authority/packs");
  await expect(page.getByTestId("authority-console")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("authority-packs-tab")).toBeVisible();

  const card = packCard(page, packName);
  await expect(
    card,
    `Pack ${packName} is missing from the catalog`
  ).toBeVisible({
    timeout: 30_000,
  });
  await card
    .getByRole("button", { name: /Review & install|Review pack/i })
    .click();
  await expect(page.getByTestId("authority-pack-preflight")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("pack-preflight-title")).toContainText(
    /Preflight:/i
  );
  await expect(page.getByTestId("pack-fingerprint")).not.toHaveText("");
}

/**
 * Install one trusted server-catalog pack through its real preflight modal.
 * The returned observation is parsed from the real install mutation response,
 * making backend relationship reconciliation part of the browser contract.
 */
export async function installAuthorityPackViaUI(
  page: Page,
  packName: string
): Promise<AuthorityPackInstallObservation> {
  await openPackPreflight(page, packName);

  const submit = page.getByTestId("pack-install-submit");
  await expect(submit).toBeVisible();
  const buttonText = (await submit.textContent())?.trim() || "";
  if (/Nothing to install/i.test(buttonText)) {
    throw new Error(
      `Pack ${packName} is already installed. This isolated E2E must start from a fresh database so every install mutation and its relationship summary can be observed.`
    );
  }

  await expect(submit).toHaveText(/Install privately/i);
  await expect(submit).toBeEnabled();
  const installRequestPromise = page.waitForRequest(
    isInstallAuthorityPackRequest,
    { timeout: 90_000 }
  );
  await submit.click();
  const installRequest = await installRequestPromise;
  const installResponse = await installRequest.response();
  if (!installResponse) {
    throw new Error(
      `InstallAuthorityPack request failed for ${packName}: ${
        installRequest.failure()?.errorText || "no response received"
      }`
    );
  }
  const payload = (await installResponse.json()) as {
    data?: {
      installAuthorityPack?: {
        ok?: unknown;
        message?: unknown;
        result?: unknown;
        pack?: { name?: unknown } | null;
      } | null;
    };
    errors?: Array<{ message?: string }>;
  };
  expect(
    installResponse.status(),
    `installAuthorityPack HTTP failure for ${packName}: ${JSON.stringify(
      payload
    )}`
  ).toBe(200);
  if (payload.errors?.length) {
    throw new Error(
      `installAuthorityPack failed for ${packName}: ${payload.errors
        .map((error) => error.message || "unknown GraphQL error")
        .join("; ")}`
    );
  }
  const mutation = payload.data?.installAuthorityPack;
  if (!mutation || mutation.ok !== true) {
    throw new Error(
      `installAuthorityPack did not succeed for ${packName}: ${
        typeof mutation?.message === "string"
          ? mutation.message
          : JSON.stringify(payload)
      }`
    );
  }
  if (mutation.pack?.name !== undefined && mutation.pack?.name !== packName) {
    throw new Error(
      `Installed pack response named ${JSON.stringify(
        mutation.pack.name
      )}; expected ${packName}`
    );
  }
  if (
    !mutation.result ||
    typeof mutation.result !== "object" ||
    Array.isArray(mutation.result)
  ) {
    throw new Error(
      `installAuthorityPack returned no structured result for ${packName}`
    );
  }
  const rawRelationships = (mutation.result as Record<string, unknown>)
    .relationships;
  if (
    !rawRelationships ||
    typeof rawRelationships !== "object" ||
    Array.isArray(rawRelationships)
  ) {
    throw new Error(
      `installAuthorityPack returned no relationship summary for ${packName}`
    );
  }
  const rawCounts = rawRelationships as Record<string, unknown>;
  const relationships = {
    created: requireNonNegativeInteger(rawCounts.created, "created"),
    updated: requireNonNegativeInteger(rawCounts.updated, "updated"),
    unchanged: requireNonNegativeInteger(rawCounts.unchanged, "unchanged"),
    preservedManual: requireNonNegativeInteger(
      rawCounts.preserved_manual,
      "preserved_manual"
    ),
    preservedBaseline: requireNonNegativeInteger(
      rawCounts.preserved_baseline,
      "preserved_baseline"
    ),
    skippedForeign: requireNonNegativeInteger(
      rawCounts.skipped_foreign,
      "skipped_foreign"
    ),
    deleted: requireNonNegativeInteger(rawCounts.deleted, "deleted"),
  };

  await expect(page.getByTestId("authority-pack-preflight")).not.toBeVisible({
    timeout: 90_000,
  });

  const card = packCard(page, packName);
  await expect(card).toContainText(/Installed privately|Partially installed/i, {
    timeout: 30_000,
  });
  return { packName, relationships };
}

export interface StartedCorpusImport {
  corpusId: number;
  testCase: AuthorityPackImportCase;
}

export interface CanonicalCorpusObservation {
  packName: string;
  corpusSlug: string;
  corpusGlobalId: string;
  canonicalKeyByDocumentId: Record<string, string>;
  providerRelationships: ProvisionalAuthorityRelationship[];
  representativeSearchText: string;
}

/**
 * Select the installed pack corpus, upload its generated export ZIP, and start
 * the targeted sideload through ImportCorpusModal.
 */
export async function uploadAuthorityCorpusExportViaUI(
  page: Page,
  testCase: AuthorityPackImportCase
): Promise<StartedCorpusImport> {
  await openPackPreflight(page, testCase.packName);

  const corpusRow = page
    .getByTestId("pack-corpus-row")
    .filter({ hasText: testCase.corpusSlug })
    .first();
  await expect(corpusRow).toBeVisible();
  await expect(corpusRow).toContainText("Installed");

  const importButton = page.getByTestId(
    `pack-import-corpus-${testCase.corpusSlug}`
  );
  await expect(importButton).toBeEnabled();
  await importButton.click();

  await expect(page.getByText("Sideload Corpus").first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    page.getByText(`Import into ${testCase.corpusTitle}`).first()
  ).toBeVisible();
  await page.getByRole("button", { name: /^Continue$/i }).click();

  const fileInput = page.locator('input[type="file"][accept=".zip"]').last();
  await fileInput.setInputFiles(testCase.exportZipPath);
  const expectedFileSize = fs.statSync(testCase.exportZipPath).size;
  expect(
    expectedFileSize,
    `Corpus export ZIP is empty on disk: ${testCase.exportZipPath}`
  ).toBeGreaterThan(0);
  const selectedFile = await fileInput.evaluate((input: HTMLInputElement) => {
    const file = input.files?.[0];
    return file ? { name: file.name, size: file.size } : null;
  });
  expect(
    selectedFile,
    `Browser file input did not retain ${testCase.exportZipPath}`
  ).toEqual({
    name: path.basename(testCase.exportZipPath),
    size: expectedFileSize,
  });
  await expect(
    page.getByText(path.basename(testCase.exportZipPath)).first()
  ).toBeVisible();

  const completionResponsePromise = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === "POST" &&
        (url.pathname === "/api/imports/corpus/" ||
          /^\/api\/imports\/chunked\/[^/]+\/complete\/$/.test(url.pathname))
      );
    },
    { timeout: 30 * 60 * 1000 }
  );

  await page.getByRole("button", { name: /Start Import/i }).click();
  const response = await completionResponsePromise;
  const body = (await response.json()) as {
    ok?: boolean;
    corpus_id?: unknown;
    error?: string;
  };
  expect(
    response.status(),
    `Corpus upload failed for ${testCase.corpusSlug}: ${JSON.stringify(body)}`
  ).toBe(202);
  expect(body.ok).toBe(true);
  const corpusId =
    typeof body.corpus_id === "number"
      ? body.corpus_id
      : Number(body.corpus_id);
  expect(
    Number.isInteger(corpusId) && corpusId > 0,
    `Upload response did not include a valid corpus_id: ${JSON.stringify(body)}`
  ).toBe(true);

  await expect(
    page.getByText(`Import into ${testCase.corpusTitle} has started.`)
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Sideload Corpus").first()).not.toBeVisible({
    timeout: 30_000,
  });
  return { corpusId, testCase };
}

/**
 * Wait for every targeted corpus import's real admin-monitor row to reach DONE.
 */
export async function waitForCorpusImportsDoneViaUI(
  page: Page,
  cases: AuthorityPackImportCase[],
  // This suite imports hundreds of publisher artifacts through the real
  // asynchronous pipeline. Keep the monitor within the spec's two-hour
  // ceiling while leaving time for its post-import GUI content audit.
  timeoutMs = 90 * 60 * 1000
): Promise<void> {
  await spaNavigate(page, "/admin/ingestion");
  await expect(page.getByText("Ingestion Monitor").first()).toBeVisible({
    timeout: 30_000,
  });
  await page.getByTestId("tab-imports").click();
  await expect(page.getByText("Corpus-Export Imports")).toBeVisible();

  await expect(async () => {
    await page.getByRole("button", { name: /^Refresh$/i }).click();

    for (const testCase of cases) {
      const row = page
        .getByRole("row")
        .filter({ hasText: testCase.corpusTitle })
        .first();
      await expect(
        row,
        `No import status row for ${testCase.corpusTitle}`
      ).toBeVisible({ timeout: 5_000 });

      const statusText = ((await row.locator("td").nth(2).textContent()) || "")
        .trim()
        .toLowerCase();
      if (statusText === "failed") {
        throw new Error(
          `Corpus import entered FAILED for ${testCase.corpusTitle}`
        );
      }
      expect(
        statusText,
        `Corpus import has not completed for ${testCase.corpusTitle}`
      ).toBe("done");
    }
  }).toPass({
    timeout: timeoutMs,
    intervals: [2_000, 5_000, 10_000, 15_000],
  });
}

/**
 * The import-monitor row reaches DONE once relationship remapping has finished.
 * A document's last asynchronous unlock/status update can still be queued at
 * that point, so a full corpus acceptance audit must also wait for every
 * imported document to become queryable.  This is intentionally a read-only
 * browser inspection; the preceding installation and import operations remain
 * real UI interactions.
 */
export async function waitForAuthorityCorpusDocumentsCompleted(
  page: Page,
  token: string,
  startedImports: StartedCorpusImport[],
  timeoutMs = 90 * 60 * 1000
): Promise<void> {
  await expect(async () => {
    for (const startedImport of startedImports) {
      const corpus = await inspectCanonicalCorpus(
        page,
        token,
        relayId("CorpusType", startedImport.corpusId)
      );
      const documents = corpus.documents.edges
        .map((edge) => edge.node)
        .filter((node): node is CorpusInspectionDocument => node !== null);

      expect(corpus.documentCount).toBe(
        startedImport.testCase.expectedDocumentCount
      );
      expect(documents).toHaveLength(
        startedImport.testCase.expectedDocumentCount
      );
      expect(
        documents.filter(
          (document) =>
            document.backendLock ||
            document.processingStatus?.toLowerCase() !== "completed"
        ),
        `Corpus documents are not all ready: ${startedImport.testCase.corpusTitle}`
      ).toEqual([]);
    }
  }).toPass({
    timeout: timeoutMs,
    intervals: [2_000, 5_000, 10_000, 15_000],
  });
}

interface GraphqlError {
  message?: string;
}

async function browserGraphql<T>(
  page: Page,
  token: string,
  query: string,
  variables: Record<string, unknown>
): Promise<T> {
  const result = await page.evaluate(
    async ({ url, bearer, document, vars }) => {
      const response = await fetch(`${url}/graphql/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${bearer}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: document, variables: vars }),
      });
      return {
        status: response.status,
        payload: (await response.json()) as unknown,
      };
    },
    {
      url: DJANGO_URL.replace(/\/$/, ""),
      bearer: token,
      document: query,
      vars: variables,
    }
  );

  expect(result.status).toBe(200);
  const payload = result.payload as {
    data?: T;
    errors?: GraphqlError[];
  };
  if (payload.errors?.length) {
    throw new Error(
      `GraphQL inspection failed: ${payload.errors
        .map((error) => error.message || "unknown error")
        .join("; ")}`
    );
  }
  if (!payload.data) {
    throw new Error("GraphQL inspection returned no data");
  }
  return payload.data;
}

interface CorpusInspectionPath {
  id: string;
  path: string;
  isCurrent: boolean;
  isDeleted: boolean;
  corpus: { id: string };
}

interface CorpusInspectionDocument {
  id: string;
  title: string | null;
  description: string | null;
  customMeta: unknown;
  isCurrent: boolean;
  backendLock: boolean;
  processingStatus: string | null;
  txtExtractFile: string | null;
  pathRecords: {
    edges: Array<{ node: CorpusInspectionPath | null }>;
  };
}

interface CorpusInspection {
  corpus: {
    id: string;
    slug: string;
    title: string;
    documentCount: number;
    documents: {
      totalCount: number;
      edges: Array<{ node: CorpusInspectionDocument | null }>;
      pageInfo: {
        hasNextPage: boolean;
        endCursor: string | null;
      };
    };
  } | null;
}

const CORPUS_CANONICAL_STATE_QUERY = `
  query AuthorityCorpusCanonicalState(
    $corpusId: ID!
    $first: Int!
    $after: String
  ) {
    corpus(id: $corpusId) {
      id
      slug
      title
      documentCount
      documents(first: $first, after: $after) {
        totalCount
        edges {
          node {
            id
            title
            description
            customMeta
            isCurrent
            backendLock
            processingStatus
            txtExtractFile
            pathRecords(first: 20) {
              edges {
                node {
                  id
                  path
                  isCurrent
                  isDeleted
                  corpus {
                    id
                  }
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
`;

async function inspectCanonicalCorpus(
  page: Page,
  token: string,
  corpusGlobalId: string
): Promise<NonNullable<CorpusInspection["corpus"]>> {
  const documentEdges: Array<{ node: CorpusInspectionDocument | null }> = [];
  const seenCursors = new Set<string>();
  let after: string | null = null;
  let corpusSnapshot: NonNullable<CorpusInspection["corpus"]> | null = null;

  do {
    const data = await browserGraphql<CorpusInspection>(
      page,
      token,
      CORPUS_CANONICAL_STATE_QUERY,
      {
        corpusId: corpusGlobalId,
        first: 100,
        after,
      }
    );
    const pageCorpus = data.corpus;
    if (!pageCorpus) {
      throw new Error(`Corpus ${corpusGlobalId} was not readable`);
    }
    if (corpusSnapshot) {
      expect(pageCorpus.id).toBe(corpusSnapshot.id);
      expect(pageCorpus.documents.totalCount).toBe(
        corpusSnapshot.documents.totalCount
      );
    } else {
      corpusSnapshot = pageCorpus;
    }
    documentEdges.push(...pageCorpus.documents.edges);

    const { hasNextPage, endCursor } = pageCorpus.documents.pageInfo;
    if (!hasNextPage) break;
    if (!endCursor || seenCursors.has(endCursor)) {
      throw new Error(
        `Corpus ${corpusGlobalId} returned an invalid repeated pagination cursor`
      );
    }
    seenCursors.add(endCursor);
    after = endCursor;
  } while (true);

  if (!corpusSnapshot) {
    throw new Error(`Corpus ${corpusGlobalId} was not readable`);
  }
  return {
    ...corpusSnapshot,
    documents: {
      ...corpusSnapshot.documents,
      edges: documentEdges,
    },
  };
}

function parseCustomMeta(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // The assertion below reports the document whose metadata was malformed.
    }
  }
  return {};
}

function relayId(typeName: string, rawId: number): string {
  return Buffer.from(`${typeName}:${rawId}`, "utf-8").toString("base64");
}

function expectSha256Metadata(
  metadata: Record<string, unknown>,
  field: string,
  canonicalKey: string
): void {
  expect(
    typeof metadata[field] === "string" &&
      SHA256_HEX_RE.test(metadata[field] as string),
    `Canonical key ${canonicalKey} has invalid custom_meta.${field}`
  ).toBe(true);
}

function parseProviderRelationships(
  metadata: Record<string, unknown>,
  packName: string,
  canonicalKey: string
): ProvisionalAuthorityRelationship[] {
  const rawRelationships = metadata.relationships;
  if (!Array.isArray(rawRelationships)) {
    throw new Error(
      `Canonical key ${canonicalKey} has non-array custom_meta.relationships`
    );
  }
  return rawRelationships.map((value, index) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(
        `Canonical key ${canonicalKey} relationship ${index} must be an object`
      );
    }
    const relationship = value as Record<string, unknown>;
    if (relationship.verified !== false) {
      throw new Error(
        `Canonical key ${canonicalKey} relationship ${index} must remain unverified`
      );
    }
    const relationshipMetadata = relationship.metadata;
    if (
      !relationshipMetadata ||
      typeof relationshipMetadata !== "object" ||
      Array.isArray(relationshipMetadata) ||
      (relationshipMetadata as Record<string, unknown>).review_status !==
        "pending_legal_review"
    ) {
      throw new Error(
        `Canonical key ${canonicalKey} relationship ${index} must remain pending_legal_review`
      );
    }
    return {
      packName,
      sourceKey: canonicalKey,
      relationshipType: requireNonEmptyString(
        relationship.relationship_type,
        "relationship_type",
        `${packName}/${canonicalKey}`
      ),
      targetKey: requireNonEmptyString(
        relationship.target_key,
        "target_key",
        `${packName}/${canonicalKey}`
      ),
    };
  });
}

interface ExtractedContentInspection {
  documentId: string;
  status: number;
  ok: boolean;
  length: number;
  forbiddenMarker: string | null;
}

async function inspectExtractedContent(
  page: Page,
  documents: CorpusInspectionDocument[]
): Promise<ExtractedContentInspection[]> {
  const results: ExtractedContentInspection[] = [];
  const batchSize = 12;

  for (let offset = 0; offset < documents.length; offset += batchSize) {
    const batch = documents
      .slice(offset, offset + batchSize)
      .map((document) => ({
        documentId: document.id,
        url: document.txtExtractFile as string,
      }));
    const batchResults = await page.evaluate(
      async ({ requests, forbiddenMarkers }) =>
        Promise.all(
          requests.map(async ({ documentId, url }) => {
            const response = await fetch(url);
            const content = await response.text();
            const forbiddenMarker =
              forbiddenMarkers.find((marker) => content.includes(marker)) ||
              null;
            return {
              documentId,
              status: response.status,
              ok: response.ok,
              length: content.trim().length,
              forbiddenMarker,
            };
          })
        ),
      {
        requests: batch,
        forbiddenMarkers: [...SYNTHETIC_LINK_ONLY_MARKERS],
      }
    );
    results.push(...batchResults);
  }
  return results;
}

/**
 * Prove canonical identity reconciliation after sideload:
 * - every expected key resolves to exactly one current document,
 * - each document has exactly one active path in the target corpus,
 * - no pack seed survives as a duplicate active path,
 * - the corpus contains exactly the scraper-declared document set,
 * - every document came through the full-content collector path, and
 * - every parser-produced text layer is non-empty and contains no synthetic
 *   link-only placeholder.
 */
export async function expectCanonicalCorpusState(
  page: Page,
  token: string,
  startedImport: StartedCorpusImport
): Promise<CanonicalCorpusObservation> {
  const corpusGlobalId = relayId("CorpusType", startedImport.corpusId);
  const corpus = await inspectCanonicalCorpus(page, token, corpusGlobalId);

  const testCase = startedImport.testCase;
  expect(corpus.slug).toBe(testCase.corpusSlug);
  expect(corpus.title).toBe(testCase.corpusTitle);

  const documents = corpus.documents.edges
    .map((edge) => edge.node)
    .filter((node): node is CorpusInspectionDocument => node !== null);
  expect(corpus.documentCount).toBe(testCase.expectedDocumentCount);
  expect(corpus.documents.totalCount).toBe(testCase.expectedDocumentCount);
  expect(documents).toHaveLength(testCase.expectedDocumentCount);

  const byCanonicalKey = new Map<string, CorpusInspectionDocument[]>();
  for (const document of documents) {
    const metadata = parseCustomMeta(document.customMeta);
    const canonicalKey = metadata.canonical_key;
    expect(
      typeof canonicalKey === "string" && canonicalKey.length > 0,
      `Document "${document.title}" is missing custom_meta.canonical_key`
    ).toBe(true);
    if (typeof canonicalKey !== "string" || canonicalKey.length === 0) continue;
    const matches = byCanonicalKey.get(canonicalKey) || [];
    matches.push(document);
    byCanonicalKey.set(canonicalKey, matches);
  }

  expect(byCanonicalKey.size).toBe(testCase.expectedDocumentCount);
  expect([...byCanonicalKey.keys()].sort()).toEqual(
    [...testCase.expectedCanonicalKeys].sort()
  );

  const providerRelationships: ProvisionalAuthorityRelationship[] = [];
  for (const canonicalKey of testCase.expectedCanonicalKeys) {
    const matches = byCanonicalKey.get(canonicalKey) || [];
    expect(
      matches,
      `Expected canonical key ${canonicalKey} must resolve exactly once`
    ).toHaveLength(1);
    const document = matches[0];
    expect(document.isCurrent).toBe(true);
    expect(document.backendLock).toBe(false);
    expect(
      document.processingStatus?.toLowerCase(),
      `Canonical key ${canonicalKey} did not finish ingestion`
    ).toBe("completed");

    const metadata = parseCustomMeta(document.customMeta);
    expect(
      metadata.ingestion_mode,
      `Canonical key ${canonicalKey} did not come from a full-content artifact`
    ).toBe("full_content");
    expect(
      metadata.rights_approved,
      `Canonical key ${canonicalKey} lacks the collector's explicit full-content authorization`
    ).toBe(true);
    expect(
      metadata.rights_status,
      `Canonical key ${canonicalKey} retained link-only rights metadata`
    ).toMatch(/^(PUBLIC_DOMAIN|LICENSED|REVIEW_REQUIRED)$/);
    expect(
      typeof metadata.source_url === "string" &&
        /^https?:\/\//.test(metadata.source_url),
      `Canonical key ${canonicalKey} is missing its publisher source URL`
    ).toBe(true);
    expectSha256Metadata(metadata, "content_hash", canonicalKey);
    expectSha256Metadata(metadata, "artifact_content_hash", canonicalKey);
    expectSha256Metadata(
      metadata,
      "publisher_source_content_hash",
      canonicalKey
    );
    expect(metadata.publisher_source_content_hash).toBe(metadata.content_hash);
    expect(
      typeof metadata.publisher_source_member === "string" &&
        metadata.publisher_source_member.length > 0,
      `Canonical key ${canonicalKey} is missing custom_meta.publisher_source_member`
    ).toBe(true);
    expect(
      typeof metadata.publisher_source_mime_type === "string" &&
        metadata.publisher_source_mime_type.length > 0,
      `Canonical key ${canonicalKey} is missing custom_meta.publisher_source_mime_type`
    ).toBe(true);
    expect(
      metadata.publisher_source_packaging,
      `Canonical key ${canonicalKey} has invalid publisher-source packaging`
    ).toMatch(/^(document|sidecar)$/);
    if (metadata.publisher_source_packaging === "document") {
      expect(metadata.publisher_source_content_hash).toBe(
        metadata.artifact_content_hash
      );
    }
    providerRelationships.push(
      ...parseProviderRelationships(metadata, testCase.packName, canonicalKey)
    );
    expect(
      typeof document.txtExtractFile === "string" &&
        document.txtExtractFile.length > 0,
      `Canonical key ${canonicalKey} has no parsed text layer`
    ).toBe(true);

    const activeTargetPaths = document.pathRecords.edges
      .map((edge) => edge.node)
      .filter(
        (node): node is CorpusInspectionPath =>
          node !== null &&
          node.corpus.id === corpus.id &&
          node.isCurrent &&
          !node.isDeleted
      );
    expect(
      activeTargetPaths,
      `Canonical key ${canonicalKey} has a duplicate or missing active seed path`
    ).toHaveLength(1);
  }

  const providerRelationshipIdentities = providerRelationships.map(
    (relationship) =>
      `${relationship.sourceKey}\u0000${relationship.relationshipType}\u0000${relationship.targetKey}`
  );
  expect(
    new Set(providerRelationshipIdentities).size,
    `${testCase.corpusSlug} contains duplicate provider relationship declarations`
  ).toBe(providerRelationshipIdentities.length);
  expect(providerRelationshipIdentities.sort()).toEqual(
    testCase.expectedProviderRelationships
      .map(
        (relationship) =>
          `${relationship.sourceKey}\u0000${relationship.relationshipType}\u0000${relationship.targetKey}`
      )
      .sort()
  );

  const extractedContent = await inspectExtractedContent(page, documents);
  expect(extractedContent).toHaveLength(testCase.expectedDocumentCount);
  for (const inspection of extractedContent) {
    const canonicalKey =
      parseCustomMeta(
        documents.find((document) => document.id === inspection.documentId)
          ?.customMeta
      ).canonical_key || inspection.documentId;
    expect(
      inspection.ok,
      `Could not read parsed publisher content for ${canonicalKey}; HTTP ${inspection.status}`
    ).toBe(true);
    expect(
      inspection.length,
      `Parsed publisher content is empty for ${canonicalKey}`
    ).toBeGreaterThan(0);
    expect(
      inspection.forbiddenMarker,
      `Parsed content for ${canonicalKey} contains a synthetic link-only placeholder`
    ).toBeNull();
  }

  const representativeDocuments = documents.filter(
    (document) => document.title === testCase.expectedDocumentTitle
  );
  expect(
    representativeDocuments,
    `Representative title must resolve exactly once in ${testCase.corpusSlug}`
  ).toHaveLength(1);
  const representativeSearchText =
    representativeDocuments[0].description?.trim() || "";
  expect(
    representativeSearchText,
    `Representative document ${testCase.expectedDocumentTitle} needs a searchable description`
  ).not.toBe("");

  return {
    packName: testCase.packName,
    corpusSlug: testCase.corpusSlug,
    corpusGlobalId,
    representativeSearchText,
    providerRelationships,
    canonicalKeyByDocumentId: Object.fromEntries(
      [...byCanonicalKey.entries()].map(([canonicalKey, [document]]) => [
        document.id,
        canonicalKey,
      ])
    ),
  };
}

interface GovernanceGraphInspection {
  governanceGraph: {
    corpora: Array<{ id: string }>;
    nodes: Array<{ id: string; documentId: string | null }>;
    edges: Array<{
      source: string;
      target: string;
      edgeType: string;
      weight: number;
    }>;
    edgeCount: number;
    truncated: boolean;
  } | null;
}

interface DocumentCanonicalKeyInspection {
  document: {
    id: string;
    customMeta: unknown;
  } | null;
}

const PRODUCTION_GOVERNANCE_GRAPH_QUERY = `
  query AuthorityProductionGovernanceGraph($corpusId: ID!) {
    governanceGraph(corpusId: $corpusId) {
      corpora {
        id
      }
      nodes {
        id
        documentId
      }
      edges {
        source
        target
        edgeType
        weight
      }
      edgeCount
      truncated
    }
  }
`;

const DOCUMENT_CANONICAL_KEY_QUERY = `
  query AuthorityDocumentCanonicalKey($documentId: ID!) {
    document(id: $documentId) {
      id
      customMeta
    }
  }
`;

function endpointCanonicalKey(
  endpoint: string,
  canonicalKeyByDocumentId: Map<string, string>
): string | undefined {
  return endpoint.startsWith("key:")
    ? endpoint.slice("key:".length)
    : canonicalKeyByDocumentId.get(endpoint);
}

/**
 * Query the production governance graph for every corpus that contains a
 * declared source key. A declaration can be installed as baseline data while
 * still being legally provisional; verified=false must keep it off this graph.
 */
export async function expectProvisionalRelationshipsExcludedFromGovernanceGraph(
  page: Page,
  token: string,
  corpusObservations: CanonicalCorpusObservation[],
  declarations: ProvisionalAuthorityRelationship[]
): Promise<void> {
  const canonicalKeyByDocumentId = new Map<string, string>();
  for (const observation of corpusObservations) {
    for (const [documentId, canonicalKey] of Object.entries(
      observation.canonicalKeyByDocumentId
    )) {
      canonicalKeyByDocumentId.set(documentId, canonicalKey);
    }
  }

  const sourceCorpusByRelationship = new Map<
    ProvisionalAuthorityRelationship,
    CanonicalCorpusObservation
  >();
  for (const declaration of declarations) {
    const sourceCorpora = corpusObservations.filter(
      (observation) =>
        observation.packName === declaration.packName &&
        Object.values(observation.canonicalKeyByDocumentId).includes(
          declaration.sourceKey
        )
    );
    expect(
      sourceCorpora,
      `Source key ${declaration.sourceKey} must resolve in exactly one imported corpus for pack ${declaration.packName}`
    ).toHaveLength(1);
    sourceCorpusByRelationship.set(declaration, sourceCorpora[0]);
  }

  const representativeCorpora = [
    ...new Map(
      [...sourceCorpusByRelationship.values()].map((observation) => [
        observation.corpusGlobalId,
        observation,
      ])
    ).values(),
  ];
  const graphByCorpusId = new Map<
    string,
    NonNullable<GovernanceGraphInspection["governanceGraph"]>
  >();

  for (const observation of representativeCorpora) {
    const data = await browserGraphql<GovernanceGraphInspection>(
      page,
      token,
      PRODUCTION_GOVERNANCE_GRAPH_QUERY,
      { corpusId: observation.corpusGlobalId }
    );
    const graph = data.governanceGraph;
    expect(
      graph,
      `governanceGraph returned null for ${observation.corpusSlug}`
    ).not.toBeNull();
    if (!graph) {
      throw new Error(
        `governanceGraph returned null for ${observation.corpusSlug}`
      );
    }
    expect(
      graph.corpora.map((corpus) => corpus.id),
      `governanceGraph did not admit the readable source corpus ${observation.corpusSlug}`
    ).toContain(observation.corpusGlobalId);
    expect(
      graph.truncated,
      `governanceGraph for ${observation.corpusSlug} was truncated; edge absence cannot prove legal gating`
    ).toBe(false);
    expect(graph.edges).toHaveLength(graph.edgeCount);
    graphByCorpusId.set(observation.corpusGlobalId, graph);

    for (const node of graph.nodes) {
      const documentId = node.documentId;
      if (!documentId || canonicalKeyByDocumentId.has(documentId)) continue;
      const documentData = await browserGraphql<DocumentCanonicalKeyInspection>(
        page,
        token,
        DOCUMENT_CANONICAL_KEY_QUERY,
        { documentId }
      );
      const canonicalKey = parseCustomMeta(
        documentData.document?.customMeta
      ).canonical_key;
      if (typeof canonicalKey === "string" && canonicalKey.length > 0) {
        canonicalKeyByDocumentId.set(documentId, canonicalKey);
      }
    }
  }

  for (const declaration of declarations) {
    const sourceCorpus = sourceCorpusByRelationship.get(declaration);
    if (!sourceCorpus) {
      throw new Error(
        `No source corpus resolved for provisional relationship ${declaration.sourceKey}`
      );
    }
    const graph = graphByCorpusId.get(sourceCorpus.corpusGlobalId);
    if (!graph) {
      throw new Error(
        `No governance graph was inspected for ${sourceCorpus.corpusSlug}`
      );
    }
    const admitted = graph.edges.filter(
      (edge) =>
        endpointCanonicalKey(edge.source, canonicalKeyByDocumentId) ===
          declaration.sourceKey &&
        edge.edgeType === declaration.relationshipType &&
        endpointCanonicalKey(edge.target, canonicalKeyByDocumentId) ===
          declaration.targetKey
    );
    expect(
      admitted,
      `Pending legal-review edge was admitted to production governanceGraph: ${declaration.sourceKey} ${declaration.relationshipType} ${declaration.targetKey}`
    ).toEqual([]);
  }
}

/**
 * Verify a representative imported document through the rendered corpus and
 * document UI, including a stable text sentinel selected by the scraper.
 */
export async function expectImportedContentViaUI(
  page: Page,
  testCase: AuthorityPackImportCase,
  corpusObservation: CanonicalCorpusObservation
): Promise<void> {
  expect(corpusObservation.packName).toBe(testCase.packName);
  expect(corpusObservation.corpusSlug).toBe(testCase.corpusSlug);

  await spaNavigate(page, "/corpuses");
  await expect(page.getByText(testCase.corpusTitle).first()).toBeVisible({
    timeout: 30_000,
  });
  await page.getByText(testCase.corpusTitle).first().click();
  await expect(page).toHaveURL(/\/c\/[^/]+\/[^/?]+/, { timeout: 30_000 });

  // The default corpus route is the Explore landing. Enter its existing
  // Manage surface, then select the URL-driven Documents tab; that is where
  // the corpus-scoped search control and virtualized document cards live.
  const navigationSidebar = page.getByTestId("navigation-sidebar");
  if (!(await navigationSidebar.isVisible().catch(() => false))) {
    const modeToggle = page.getByTestId("landing-mode-toggle");
    await expect(modeToggle).toBeVisible({ timeout: 30_000 });
    await modeToggle.click();
  }
  await expect(navigationSidebar).toBeVisible({ timeout: 30_000 });
  const documentsNavigation = page.locator('[data-item-id="documents"]');
  await expect(documentsNavigation).toBeVisible({ timeout: 30_000 });
  await documentsNavigation.click();
  await expect(page).toHaveURL(/[?&]tab=documents(?:&|$)/, {
    timeout: 30_000,
  });

  // Corpus grids virtualize and page large collections (the ERCOT revision
  // corpus alone has well over 100 documents). Drive the real corpus search so
  // the representative document is visible regardless of its page/order.
  const search = page.getByPlaceholder("Search for document in corpus...");
  await expect(search).toBeVisible({ timeout: 30_000 });
  await search.fill(corpusObservation.representativeSearchText);

  const documentCard = page
    .locator("[data-testid='document-card']")
    .filter({ hasText: testCase.expectedDocumentTitle })
    .first();
  await expect(documentCard).toBeVisible({ timeout: 30_000 });
  const documentTitle = documentCard
    .getByText(testCase.expectedDocumentTitle, { exact: true })
    .first();
  await expect(documentTitle).toBeVisible({ timeout: 30_000 });
  await documentTitle.click();
  await expect(page).toHaveURL(/\/d\/[^/]+\/.+/, { timeout: 30_000 });
  await expect(
    page.getByText(testCase.expectedDocumentTitle, { exact: true }).first()
  ).toBeVisible();

  await expect(
    page.locator("body"),
    `Rendered document is missing content sentinel for ${testCase.corpusSlug}`
  ).toContainText(testCase.expectedContentText, {
    timeout: 60_000,
    useInnerText: true,
  });
}
