# Mobile DocumentKnowledgeBase — Design Spec

**Date:** 2026-05-20
**Status:** Approved design — ready for implementation planning
**Component:** `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`

## 1. Context & problem

`DocumentKnowledgeBase` (DKB) is the most complex view in the app — a PDF viewer
with an annotation layer, a knowledge/summary layer, an AI chat, and several
side panels (annotations feed, notes, discussions, analyses, extracts).

A look-and-feel audit (driven through the real component at a 390px viewport)
found that **there is no mobile layout**. The desktop floating-overlay
architecture is rendered as-is on a phone:

- The PDF loads at ~61% zoom — body text is unreadable.
- 6+ independent floating control clusters sit on top of the document, which
  *is* the entire viewport: `ZoomControls`, `FloatingDocumentInput`,
  `FloatingDocumentControls` (right rail), the FAB speed-dial,
  `FloatingSummaryPreview`, `EnhancedLabelSelector`, annotation pills.
- Opening any one control piles another opaque overlay onto the document.

**Root cause:** there is no mobile layout *owner*. `DocumentKnowledgeBase`
renders one layout, and several floating child components each branch on
`isMobile` independently (`FloatingDocumentControls` has a mobile speed-dial
branch, `FloatingSummaryPreview` has its own, `MobileSidebarTabs` vs
`DesktopSidebarTabs`). Nobody coordinates them, so they accumulate as
overlapping overlays. Mobile support is not *absent* — it is *uncoordinated*.

## 2. Goals & non-goals

### Goals

- A real mobile layout for the DKB: the document gets the full viewport;
  controls and surfaces are composed deliberately, not floated.
- Mobile is a **consumption + light-review** surface — read the document,
  read the summary/annotations, ask the AI, and inspect annotation detail.
  Vote/approve remain reachable via the existing in-viewer highlight tooltip.
- Fix the root cause: a single mobile layout *owner*, not N uncoordinated
  `isMobile` branches.

### Non-goals (explicitly out of scope)

- **Annotation authoring on mobile** — no token selection, no label picker.
  Creating new annotations is not available on mobile.
- **Analyses & Extracts on mobile** — these compute/authoring panels are not
  rendered on mobile.
- **Desktop behavior changes** — desktop is untouched except for a verbatim
  extraction (see §6).
- **Tablet (≥768px)** — keeps the desktop layout. The existing
  `isMobile = width < 768` breakpoint is unchanged.
- Offline / performance work beyond what already exists.
- The desktop polish items (issues #1734 / #1735 / #1736) — tracked separately.

## 3. Use case & surface tiering

The primary mobile job is **read & ask**, with some **review** (inspect
annotation detail; vote/approve via the in-viewer highlight tooltip).
Surfaces are tiered accordingly:

| Tier | Surfaces | Treatment |
|------|----------|-----------|
| 1 — first-class | Document, Summary/Knowledge, Chat, Annotations list | One tap from the document |
| 2 — secondary | Discussions, Notes, in-document search, document index | Reachable in ≤2 taps |
| 3 — not on mobile | Analyses, Extracts, annotation authoring | Not rendered |

Within Tier 2, **in-document search and the section index** are
*document-navigation* aids and live in the Document tab's toolbar;
**Discussions and Notes** are separate content surfaces and live in "More".

## 4. Navigation model — "Tabs + persistent Ask bar"

Selected approach (over a plain tab bar, and over draggable bottom sheets).
Rationale: the dominant job is *read & ask*, so "ask" should be omnipresent
rather than buried behind a tab; and full-height reading surfaces do not
justify the drag/snap machinery a multi-snap sheet model would require.

### Fixed chrome (always present)

- **Top bar** — back · truncated document title · `⋯` overflow. The overflow
  holds document *actions* (versions, add-to-corpus, share) — not navigation.
- **Ask bar** — a persistent input above the tab bar. Tapping it expands Chat
  as a full-height sheet. Available from every tab.
- **Bottom tab bar** — four tabs: **Document · Summary · Annotations · More**.

### Surface placement

- **Document** tab — full-viewport PDF with a slim in-tab toolbar holding
  **Sections** (index), **Find** (in-document search), and zoom.
- **Summary** tab — the knowledge-layer summary, full-screen scroll.
- **Annotations** tab — a scrollable list of annotation rows, full-screen.
- **More** tab — opens a sheet listing **Discussions**, **Notes**, and
  document info/versions.
- **Chat** — the Ask bar (not a tab).
- Analyses / Extracts / annotation-authoring controls — not rendered.

## 5. The four surfaces

### Sheets — interaction model

"Sheet" means a **plain full-height slide-up panel**: one open animation, one
close button, one sheet at a time. It is *not* a draggable multi-snap sheet
(that complexity is why the bottom-sheet navigation approach was rejected).
While a sheet is open it covers the tab bar and Ask bar; closing it returns
the user to the tab they were on.

### Document tab

- Full-viewport PDF. **Default zoom = fit-to-width** so the document is
  readable on load.
- Annotations render as highlights (read).
- Tapping a highlight opens the **annotation detail sheet** (see below).
- In-tab toolbar: Sections, Find, zoom. Pinch-zoom still works.

### Summary tab

- The knowledge-layer summary, full-screen scroll. Version switching (when
  multiple versions exist) lives in the top-bar `⋯` menu.

### Annotations tab

- A scrollable list of annotation rows (quoted text, label, relationships,
  page). One filter affordance at the top (All / by label).
- Tapping a row opens the **annotation detail sheet**.

### Chat (Ask bar → Chat sheet)

- The Ask bar expands into a full-height Chat sheet: the conversation, the
  composer, and AI responses with source citations.
- Source chips are tappable: tapping one closes the sheet and jumps the
  Document tab to the cited page/annotation.

### Annotation detail sheet (the review / "B" capability)

- **One shared component** (`MobileAnnotationDetail`), opened two ways:
  tapping a highlight in the Document tab, or tapping a row in the
  Annotations tab.
- Contents: it reuses the existing desktop `HighlightItem` card — quoted
  text, label, relationships, and page.
- Vote and Approve remain reachable on the Document tab via the existing
  in-viewer highlight tooltip; they are not duplicated into this sheet.

> **Scope note:** Annotation-level commenting does not exist anywhere in the
> OpenContracts codebase — commenting is document/corpus-level only — and
> vote/approve are not a reusable panel (they live in the in-viewer highlight
> tooltip). This mobile-layout initiative is a *layout* effort, not a
> collaboration-feature effort, so building an annotation comment thread or a
> dedicated vote/approve panel was deliberately left out of scope. The mobile
> annotation detail sheet surfaces the existing `HighlightItem` card;
> vote/approve stay on the existing in-viewer highlight tooltip.

## 6. Component architecture

`DocumentKnowledgeBase` becomes a thin **data + shared-state owner + layout
switch**. It keeps owning the data hooks and the shared state, and renders
one of two layouts:

```
DocumentKnowledgeBase            — owns data hooks + shared state; renders:
  isMobile ? <MobileDocumentLayout/> : <DesktopDocumentLayout/>

knowledge_base/document/layouts/
  DesktopDocumentLayout.tsx      — today's render, extracted verbatim
  MobileDocumentLayout.tsx       — NEW: owns the mobile chrome
  mobile/
    MobileTabBar.tsx
    MobileAskBar.tsx
    MobileSheet.tsx              — generic full-height slide-up panel
    MobileDocToolbar.tsx         — Sections / Find / zoom
```

(Directory layout follows the existing conventions in
`knowledge_base/document/` — `document_kb/`, `layers/`, `right_tray/`,
`styled/`.)

### Surfaces are shared; only the chrome differs

The PDF viewer, knowledge/summary layer, chat, annotation feed, and
annotation-detail components are the **same components desktop uses**.
`MobileDocumentLayout` composes them with mobile chrome.

The desktop-only floating pieces — `FloatingDocumentControls`,
`FloatingSummaryPreview`, `FloatingDocumentInput`, the sidebar rail, the
`ZoomControls` widget, `EnhancedLabelSelector` — **stop rendering on mobile**,
and their existing `isMobile` branches are **deleted**. This is a net code
reduction in those files and removes the dead branches.

### Mobile re-skins the existing state machine — it does not fork it

The DKB already has `activeLayer`, `showRightPanel`, `sidebarViewMode`,
`selectedAnnotation`, and `zoomLevel`. Mobile maps onto them:

| Mobile UI | Existing state |
|-----------|----------------|
| Document tab | `activeLayer = "document"` |
| Summary tab | `activeLayer = "knowledge"` |
| Annotations tab | `sidebarViewMode = "feed"` (rendered full-screen) |
| Ask bar → Chat sheet | `sidebarViewMode = "chat"` |
| Annotation detail sheet | `selectedAnnotation` set |
| More → Discussions / Notes | `sidebarViewMode = "discussion"` / `"notes"` |

Chat, annotation, and summary logic stay single-sourced — mobile is a
different *presentation* of the same state, not a parallel implementation.

## 7. Sequencing & risk

1. **Extract `DesktopDocumentLayout` as a pure verbatim move.** This is the
   only step that can regress desktop. Record a green desktop test baseline
   first; the same suite must pass unchanged afterward.
2. **Build `MobileDocumentLayout` and the mobile chrome** alongside it. This
   is mostly new code — low regression risk, since it replaces a broken
   experience.
3. **Delete the `isMobile` branches** from the floating components once they
   are desktop-only.

## 8. Testing plan

Testing is a first-class deliverable of the implementation plan.

### Desktop regression gate

The `DesktopDocumentLayout` extraction is a pure verbatim move. Run the
existing DKB component-test suite to record a green baseline before the
extraction; the **same suite must pass unchanged** afterward. That equality
is the proof the extraction did not alter desktop behavior.

### New mobile component tests

Mounted through `DocumentKnowledgeBaseTestWrapper` at a 390px viewport
(Playwright CT, `--reporter=list`):

- **Navigation:** each tab (Document / Summary / Annotations / More) activates
  its surface; tab bar and Ask bar are always present; the `isMobile`
  breakpoint renders `MobileDocumentLayout`, not the desktop layout.
- **Ask → Chat:** the Ask bar expands to the Chat sheet; submitting a message
  routes to `sidebarViewMode="chat"`; a source chip closes the sheet and
  jumps the Document tab.
- **Annotation review:** tapping a highlight opens the detail sheet; tapping
  an Annotations-list row opens the *same* sheet; the sheet renders the
  existing `HighlightItem` card (quoted text, label, relationships, page).
- **Sheets:** an open sheet covers the chrome; closing returns to the prior
  tab; only one sheet is open at a time.
- **Layout invariants:** no horizontal overflow at 390px; the document
  defaults to fit-to-width; no floating overlays leak in.
- **Absence assertions:** Analyses, Extracts, the label selector, the FAB
  speed-dial, and the right rail **do not render** on mobile — asserted
  explicitly, since absence is a real requirement here.

### Unit-level

The tab↔state mapping table in §6 gets a focused test: each mobile nav
action sets exactly the expected `activeLayer` / `sidebarViewMode` /
`selectedAnnotation`.

### Layout audit re-run

Re-run the Playwright audit drive at 390px against the branch, asserting
`overflowers == []`, and capture before/after screenshots via the
`docScreenshot` utility so the mobile DKB states are recorded in the docs.

## 9. Success criteria

- The document is readable on load (fit-to-width default zoom).
- Zero floating overlays cover the document on mobile.
- Tier-1 surfaces reachable in ≤1 tap; Tier-2 in ≤2 taps.
- No horizontal overflow at a 390px viewport.
- The existing desktop DKB tests still pass, unchanged.
