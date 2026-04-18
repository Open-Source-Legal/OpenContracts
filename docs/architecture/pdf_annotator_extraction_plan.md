# Extract `PdfAnnotator` into a Standalone React NPM Package

## Context

OpenContracts' PDF rendering and annotating component is a substantial, well-engineered subsystem (virtualized page rendering, token-based selection, annotation drawing, relationship visualization, PAWLs integration) that today lives inside `frontend/src/components/annotator/`. It is tightly coupled to OpenContracts' Apollo GraphQL schema, Apollo reactive vars, `react-router`, and REST helpers — which makes it unusable outside this monorepo.

The goal is to lift the PDF-specific portion into a standalone React npm package, `@opencontracts/pdf-annotator`, so:
- Third parties can embed PDF annotation in their own apps.
- Multiple annotator instances can mount on the same page without atom collisions.
- The OpenContracts app becomes thinner and the PDF subsystem gets a stable, documented public API.

DOCX and TXT renderers, analyses/extracts logic, and the chat-source layer remain in the host app.

---

## Recommended Approach

**Yarn workspace inside the existing monorepo** at `packages/pdf-annotator/`. Rationale: the package will co-evolve with `DocumentKnowledgeBase.tsx`, shares the TS/React toolchain, and can still be published to npm. A separate repo is premature.

Build with **tsup** (dual CJS/ESM + `.d.ts`). Use **Jotai `<Provider>` scoping** so every mount gets its own atom store. Decouple from Apollo/router/reactive-vars by introducing a single **`actions: AnnotatorActions`** adapter prop plus controlled data props.

---

## Target Package Layout

```
packages/pdf-annotator/
  package.json              # @opencontracts/pdf-annotator, exports field, peerDeps
  tsconfig.json / tsconfig.build.json
  tsup.config.ts
  vitest.config.ts
  playwright-ct.config.ts
  README.md
  src/
    index.ts                # public barrel
    PdfAnnotator.tsx        # top-level component (wraps Jotai Provider)
    types/                  # annotations.ts, pdf.ts, enums.ts, actions.ts, permissions.ts
    atoms/                  # was annotator/context/ (PDF-relevant subset)
    hooks/                  # AnnotationHooks.ts rewritten to call props.actions.*
    renderers/pdf/          # PDF.tsx, PDFPage.tsx, SelectionLayer.tsx
    display/components/     # Selection, SelectionBoundary, Tokens, SearchResult, TextBlockHighlight, ...
    sidebar/                # HighlightItem, RelationItem, RelationHighlightItem, AnnotationImagePreview, ...
    labels/                 # EnhancedLabelSelector, ViewLabelSelector
    controls/               # AnnotationControls
    components/             # SelectionActionMenu, modals/EditLabelModal
    search_widget/          # SearchWidgetStyles.css
    utils/                  # transform.ts, textBlockEncoding.ts, pawls.ts, permissions.ts
    __tests__/              # vitest + ct/ (Playwright)
```

---

## Public API (sketch)

```ts
// packages/pdf-annotator/src/types/actions.ts
export interface AnnotatorActions {
  createAnnotation(input: CreateAnnotationInput): Promise<ServerTokenAnnotation>;
  updateAnnotation(id: string, patch: UpdateAnnotationInput): Promise<ServerTokenAnnotation>;
  deleteAnnotation(id: string): Promise<void>;
  addDocTypeAnnotation(labelId: string): Promise<DocTypeAnnotation>;
  removeRelationship(id: string): Promise<void>;
  updateRelations(ops: RelationOp[]): Promise<RelationGroup[]>;
  approveAnnotation?(id: string): Promise<void>;
  rejectAnnotation?(id: string): Promise<void>;
  fetchPawls?(url: string): Promise<PageTokens[]>; // optional loader
}

export interface PdfAnnotatorProps {
  pdfUrl: string;
  pawls?: PageTokens[];                 // or pass actions.fetchPawls
  annotations: ServerTokenAnnotation[];
  relations: RelationGroup[];
  docTypeAnnotations?: DocTypeAnnotation[];
  labelSet: AnnotationLabelType[];
  permissions: PermissionTypes[];
  readOnly?: boolean;
  showStructural?: boolean;
  showBoundingBoxes?: boolean;
  showLabels?: LabelDisplayBehavior;
  initialPage?: number;
  scrollToAnnotationId?: string;        // controlled
  searchText?: string;
  actions: AnnotatorActions;
  onAnnotationSelect?(id: string | null): void;
  onError?(err: Error, ctx: string): void;
}

export const PdfAnnotator: React.FC<PdfAnnotatorProps>;
// Secondary named exports: PdfAnnotatorSidebar, AnnotationControls,
// PdfAnnotatorProvider (for advanced composition), all types.
```

---

## Decoupling Strategy

| Current coupling | Replacement |
|---|---|
| 9 Apollo `useMutation` calls in `hooks/AnnotationHooks.tsx` | `props.actions.*` methods. Hook rewritten to call adapter + update Jotai atoms optimistically. |
| Apollo reactive vars in `graphql/cache` (12 files import these — see list below) | Jotai atoms inside package, hydrated from controlled props (`showStructural`, `showBoundingBoxes`, `showLabels`, `selectedAnnotationId`, `searchText`). `authToken` removed — host fetches resources. |
| `useNavigate` / `useLocation` in `UISettingsAtom.tsx`, `AnalysisHooks.tsx` | Removed. Host owns deep-linking via `scrollToAnnotationId` + `onAnnotationSelect`. |
| `axios` + `documentCacheManager` in `api/rest.ts`, `api/cachedRest.ts` | Stays in host. Package accepts `pawls` prop or calls `actions.fetchPawls`. |
| Module-level Jotai atoms (global state) | Same atom definitions wrapped by `<Provider>` inside `PdfAnnotator.tsx` — each mount gets its own scoped store. Fixes existing multi-instance collision bug as a side benefit. |
| `CorpusAtom`, `ChatSourceAtom`, `AnalysisAtoms` consumed outside annotator | Only a slim subset of `CorpusAtom` (labelset + permissions) moves into the package. The rest stays in host. |

Files currently importing `graphql/cache` (all must be audited during Phase A):
`components/wrappers/DocxAnnotatorWrapper.tsx` (stays in host), `components/wrappers/TxtAnnotatorWrapper.tsx` (stays in host), `context/UISettingsAtom.tsx`, `display/components/Selection.tsx`, `hooks/__tests__/AnalysisHooks.sync.test.tsx` (stays), `hooks/__tests__/useClearTextBlockOnInteraction.test.tsx`, `hooks/AnalysisHooks.tsx` (stays), `hooks/useAnnotationImages.tsx`, `hooks/useClearTextBlockOnInteraction.ts`, `labels/EnhancedLabelSelector.tsx`, `renderers/pdf/PDFPage.tsx`, `sidebar/SingleDocumentExtractResults.tsx` (stays).

---

## File Disposition

**Move into package** (PDF-specific): `renderers/pdf/*`, atoms (`DocumentAtom`, `AnnotationAtoms`, `UISettingsAtom`, `AnnotationControlAtoms`, `AnnotationRefsAtoms`, subset of `CorpusAtom`), hooks (`AnnotationHooks.tsx` rewritten, `useAllAnnotations`, `useVisibleAnnotations`, `useAnnotationRefs`, `useAnnotationImages`, `useClearTextBlockOnInteraction`, `useTextSearch`, `useUISettings`, `useRelationshipActions`), `display/components/*` (PDF-relevant), `sidebar/HighlightItem|RelationItem|RelationHighlightItem|AnnotationImagePreview|ModalityBadge|common`, `labels/EnhancedLabelSelector|ViewLabelSelector`, `controls/AnnotationControls`, `components/SelectionActionMenu|modals/EditLabelModal`, `types/*`, PDF tests. Also copy `frontend/src/utils/transform.ts` and `frontend/src/utils/textBlockEncoding.ts`.

**Stay in host** (`frontend/src/components/annotator/`): `renderers/docx/*`, `renderers/txt/*`, `components/wrappers/DocxAnnotatorWrapper.tsx`, `TxtAnnotatorWrapper.tsx`, `display/viewer/DocumentViewer.tsx`, `display/components/AnnotationList.tsx`, `ChatSourceResult.tsx`, `ChatSourceTokens.tsx`, `hooks/AnalysisHooks.tsx`, `context/AnalysisAtoms.tsx`, `context/ChatSourceAtom.tsx`, `sidebar/SingleDocumentExtractResults.tsx`, `sidebar/CellEditor.tsx`, `api/rest.ts`, `api/cachedRest.ts`.

**Delete** after consumers migrate: original copies of files that moved into the package.

Package owns canonical types (`ServerTokenAnnotation`, `RelationGroup`, `DocTypeAnnotation`, `PDFPageInfo`, `PageTokens`, `TokenId`, `BoundingBox`, `AnnotationLabelType`, `PermissionTypes`, `LabelDisplayBehavior`). Host imports types from the package, not the other way around.

---

## Build Config (tsup + package.json)

- `"main": "./dist/index.cjs"`, `"module": "./dist/index.mjs"`, `"types": "./dist/index.d.ts"`.
- `"exports"` conditional map for CJS/ESM/types + `./styles.css`.
- `peerDependencies`: `react ^18`, `react-dom ^18`, `styled-components ^6`, `jotai ^2`, `pdfjs-dist ^4`.
- `dependencies`: `lucide-react`, `polished`, `react-window`, `react-virtualized-auto-sizer`, `lodash` (submodule-scoped), `fuse.js` (if search stays in-package).
- `"sideEffects": ["*.css"]`.
- Scripts: `build` (tsup --dts), `test` (vitest), `test:ct` (playwright), `typecheck` (tsc --noEmit).
- Document that the consumer must configure `pdfjs-dist` `GlobalWorkerOptions.workerSrc`.

---

## Migration Phases (Two PRs)

The work ships as **two separate pull requests**, in order:

- **PR #1 — Regression Net Only** (Phase 0 below). No production code changes. Pure test additions against the existing in-tree component. Review merits: does the net actually pin down current behavior? Is coverage sufficient? Must land and run green on `main` before PR #2 opens.
- **PR #2 — The Extraction** (Phases A → B → C below). Moves code into `packages/pdf-annotator/`, introduces the adapter, switches `DocumentKnowledgeBase`. PR #1's regression net travels with the code (some tests stay host-side for the adapter wiring, others move into the package). **Acceptance gate: every Phase-0 test still passes.**

This split means reviewers of PR #2 can trust that a green CI literally means "same behavior" — because PR #1 is what defined "same behavior" in executable form.

---

### PR #1 — Phase 0: Build a Behavior Regression Net

Rationale: the surest way to prove "same behavior after refactor" is to lock current behavior in with tests *while the code is still in one piece*. These tests are written against the in-tree component at its current import paths, stay green through Phase A, and are then moved into the package alongside the code they cover (Phase B). If any of them fail after the move, we have a precise, behavioral regression signal — not just a type error.

Coverage targets (add only what's missing; audit existing tests first):

1. **Rendering & virtualization** (Playwright CT, mount through `DocumentKnowledgeBaseTestWrapper`)
   - Mount a fixture PDF + PAWLs, assert only visible pages render (DOM page count ≈ overscan window).
   - Scroll to last page; assert binary-search visible-range picks the right pages at each zoom level.
   - Zoom in/out; assert height cache invalidation and re-layout.
2. **Token selection & annotation creation**
   - `page.mouse` drag across tokens on page N; assert `SelectionActionMenu` appears with correct label choices and that submitting fires the `createAnnotation` mutation (or, post-refactor, `actions.createAnnotation`).
   - Drag across a page boundary; assert multipage annotation JSON is correct.
   - Readonly mode: drag produces no menu.
3. **Existing annotation interactions**
   - Click highlight → selection fires, two-phase scroll-to-annotation lands it in view.
   - Edit label via modal; assert `updateAnnotation` called with expected patch.
   - Delete via context action; assert `deleteAnnotation` and removal from `pdfAnnotationsAtom`.
   - Approve / reject flows for annotations with approval UI.
4. **Relationships**
   - Render a `RelationGroup` spanning two annotations across pages; assert connecting lines render and `RelationHighlightItem` appears in sidebar.
   - Remove relationship; assert `removeRelationship` fires.
5. **Structural annotations & visibility toggles**
   - Toggle `showStructural`, `showBoundingBoxes`, `showLabels`; snapshot DOM class/attribute to confirm visibility rules.
   - `showSelectedAnnotationOnly` toggle hides the rest.
6. **Search**
   - Set `searchText`; assert `SearchResult` highlights render and active-match navigation works.
7. **Permissions**
   - Extend `SelectionLayer.permissions.test.tsx` coverage to include relationship creation and doc-type assignment paths.
8. **Hooks (vitest)**
   - `useVisibleAnnotations` with varying filter state — include the structural + selection-forced-visibility paths.
   - `usePdfAnnotations` reducer-style updates preserve immutability of `PdfAnnotations` instances.
   - `useClearTextBlockOnInteraction` already has a test; extend it if branches are uncovered.
   - `useTextSearch` matching/navigation.
   - `textBlockEncoding.ts` round-trip tests.
9. **Multi-instance** (new, reveals the current global-atoms bug)
   - Mount two `DocumentKnowledgeBase`s — document the current failure mode so Phase A's Jotai `<Provider>` scoping has an explicit before/after signal.

Exit criteria for PR #1 (Phase 0):
- Coverage report for `frontend/src/components/annotator/renderers/pdf/`, `display/components/`, `hooks/`, and `types/pdf.ts` at ≥ 85 % lines / ≥ 80 % branches (via `yarn test:coverage:unit` and `yarn test:coverage:ct`). Numbers captured in the PR description as the **frozen baseline** for PR #2.
- All new CT specs use `--reporter=list` (per `CLAUDE.md` pitfall #1).
- No snapshot tests for DOM shape unless intentionally stable (prefer behavioral assertions).
- All tests green on `main` with no code changes.
- PR #1 **must be merged to `main`** before PR #2 is opened.

These tests become the acceptance gate for PR #2: after Phase A and Phase B, **every one of them must still pass** — first in the host app (Phase A), then from inside the package (Phase B).

---

### PR #2 — The Extraction

#### Phase A — Scaffold (host untouched, CI stays green)
1. Add root `package.json` with `"workspaces": ["frontend", "packages/*"]`; convert `frontend/` to a workspace member.
2. Create `packages/pdf-annotator/` skeleton (package.json, tsconfig, tsup config, vitest config).
3. **Copy** PDF-relevant files from `frontend/src/components/annotator/` into `packages/pdf-annotator/src/` — do not delete originals yet.
4. Rewrite imports to package-relative. Strip every Apollo hook, router hook, and `graphql/cache` import. Thread `AnnotatorActions` through the hooks; replace reactive vars with Jotai atoms hydrated from props.
5. Add `<Provider>` wrapper in `PdfAnnotator.tsx`.
6. `yarn workspace @opencontracts/pdf-annotator build && test` green in isolation.

#### Phase B — Adapter + Consumer Switch
1. Create `frontend/src/adapters/pdfAnnotatorActions.ts` implementing `AnnotatorActions` by wrapping the existing Apollo mutations and `api/cachedRest.ts`.
2. Refactor `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx` to import from `@opencontracts/pdf-annotator`, construct `actions`, pass controlled data props.
3. Delete the original files from `frontend/src/components/annotator/` that moved to the package. Keep DOCX/TXT, analyses, chat-source.
4. Run frontend typecheck, vitest, and the full Playwright component test suite.

#### Phase C — Publish
1. `README.md` with props reference, quick start, pdfjs worker configuration note.
2. CHANGELOG at `0.1.0`.
3. `npm publish --access public` from the package dir (or via GitHub Action).

---

## Critical Files to Modify

- `/home/user/OpenContracts/package.json` (NEW — workspace root)
- `/home/user/OpenContracts/frontend/package.json` (add dep on workspace package)
- `/home/user/OpenContracts/frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx` (switch to package consumer)
- `/home/user/OpenContracts/frontend/src/adapters/pdfAnnotatorActions.ts` (NEW adapter)
- `/home/user/OpenContracts/frontend/src/components/annotator/hooks/AnnotationHooks.tsx` (source of the rewrite — becomes `packages/pdf-annotator/src/hooks/AnnotationHooks.ts` calling `props.actions.*`)
- `/home/user/OpenContracts/frontend/src/components/annotator/context/AnnotationAtoms.tsx`, `UISettingsAtom.tsx`, `DocumentAtom.tsx`, `AnnotationControlAtoms.tsx`, `AnnotationRefsAtoms.tsx`, `CorpusAtom.tsx` (trimmed)
- `/home/user/OpenContracts/frontend/src/components/annotator/renderers/pdf/PDF.tsx`, `PDFPage.tsx`, `SelectionLayer.tsx`
- `/home/user/OpenContracts/frontend/src/components/annotator/types/annotations.ts`, `types/pdf.ts`, `types/enums.ts`
- `/home/user/OpenContracts/frontend/src/utils/transform.ts`, `textBlockEncoding.ts` (copy into package)

## Existing Utilities to Reuse (do not rewrite)

- `frontend/src/utils/transform.ts` — `scaled()`, `normalizeBounds()`, `doOverlap()`, `spanningBound()` (copy into package).
- `frontend/src/utils/textBlockEncoding.ts` — `decodeTextBlock`, `textBlockToBounds`, `encodeTextBlock`, `textBlockFromTokensByPage` (copy into package).
- `PDFPageInfo` class in `frontend/src/components/annotator/types/pdf.ts` (move into package).
- Existing tests: `SelectionLayer.permissions.test.tsx`, `HighlightItem.scroll.test.tsx`, `useClearTextBlockOnInteraction.test.tsx`, `types/__tests__/pdf.test.ts` move into the package test suite.

---

## Verification

**PR #1 (Regression Net):**
1. `yarn workspace gui3 test:coverage:unit` and `test:coverage:ct` — meet the coverage thresholds above.
2. All new tests green on `main` with no production code changes.
3. Baseline coverage numbers captured in the PR description.

**PR #2 (Extraction):**
1. **Phase 0 regression net (merged in PR #1) is green on the branch** before any extraction work merges — this is the behavioral baseline.
2. `yarn workspace @opencontracts/pdf-annotator build` — package emits CJS + ESM + `.d.ts` without errors.
3. `yarn workspace @opencontracts/pdf-annotator test` — **every Phase-0 test that moved into the package still passes**; new package-only specs (e.g. `PdfAnnotator.readonly`, multi-instance) pass.
4. `yarn workspace gui3 typecheck` — host compiles against the package's emitted `.d.ts`.
5. `yarn workspace gui3 test:ct --reporter=list` — the remaining host-side Phase-0 tests (those mounted through `DocumentKnowledgeBaseTestWrapper` verifying the adapter wiring) still pass.
6. Coverage delta check: post-migration line/branch coverage for PDF code must be within 2 pp of the Phase-0 baseline — if it drops further, a test moved but lost meaning during the rewrite.
7. Manual smoke via the authenticated-Playwright pattern documented in `CLAUDE.md`: navigate to a corpus document, create/edit/delete an annotation, create a relationship; observe the host-side adapter fires the correct GraphQL mutations (network tab or MSW).
8. Multi-instance smoke: mount two `<PdfAnnotator>` components in a Storybook/demo page — selection and zoom remain independent, proving Jotai `<Provider>` scoping works.
9. Bundle audit (`tsup --metafile` + `esbuild-visualizer`) — confirm no `@apollo/client`, `react-router`, or `axios` in the published bundle.

---

## Risks and Open Questions

- **Hidden reactive-var reads**: components deep in `display/` may read `graphql/cache` directly; must grep and replace all during Phase A (12 files identified).
- **`utils.ts` is a grab-bag**: `createTokenStringSearch` and friends may mix PDF + DOCX logic. Audit and split cleanly before moving.
- **pdfjs worker**: package must not assume a bundler; README must document `GlobalWorkerOptions.workerSrc` config.
- **styled-components theme**: if components rely on `props.theme.*`, document the required theme shape or inline fallbacks.
- **Search widget scope**: `useTextSearch.tsx` currently reads a host reactive var. Plan treats `searchText` as a controlled prop — confirm UX is OK with external search bars, else expose an in-package search bar.
- **SSR**: do any consumers need SSR? If yes, tsup needs `react-server` condition and pdfjs must lazy-load.
- **Naming**: `@opencontracts/pdf-annotator` (scoped) vs. vendor-neutral `pdf-annotator`. If neutral, rename `ServerTokenAnnotation` → `TokenAnnotation` on the way out.
- **Backward-compat shim**: consider keeping `frontend/src/components/annotator/renderers/pdf/PDF.tsx` as a re-export stub during Phase B to minimize diff churn, then delete in Phase C.
