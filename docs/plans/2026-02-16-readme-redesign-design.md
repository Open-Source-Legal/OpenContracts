# README Redesign Design

## Problem

The current README leads with old GIFs and static screenshots that aren't sourced from the auto-screenshot pipeline. It doesn't showcase the v3 features (AI agents, discussions, analytics, badges). The structure buries the visual impact.

## Design

### Structure

1. **Header** — Logo, tagline, badges (keep existing)
2. **Hero** — `landing--discovery-page--anonymous.png` (already exists in auto/)
3. **Feature Showcase** — 5 sections, each with heading + 1-2 sentences + auto-screenshot
4. **See it in Action** — Existing GIFs (annotation flow, text processing)
5. **Getting Started** — Docker quick start
6. **Documentation** — Link table
7. **Architecture** — Collapsed `<details>` with pipeline/data format diagrams
8. **Footer** — License, acknowledgements, sponsor

### Feature Showcase Screenshots

| # | Feature | Screenshot Name | Source | Status |
|---|---------|----------------|--------|--------|
| 1 | Document Annotation | `readme--document-annotator--with-pdf` | `DocumentKnowledgeBase.ct.tsx` "PDF document renders PDF annotator component" (line 529) | **New** |
| 2 | Corpus Home | `readme--corpus-home--with-chat` | `CorpusHome.ct.tsx` "renders landing view with chat bar and quick actions" (line 304) | **New** |
| 3 | AI Agents | `threads--agent-message--response` | `MessageItem.ct.tsx` | Exists |
| 4 | Discussions | `discussions--thread-list--with-threads` | `DocumentDiscussionsContent.ct.tsx` | Exists |
| 5 | Analytics | `corpus--analytics--dashboard` | `CorpusTabs.ct.tsx` | Exists |

### New Screenshots Needed

**`readme--document-annotator--with-pdf`**: Add `docScreenshot` to the "PDF document renders PDF annotator component" test (line 529). Capture after PDF canvas renders. Full page to show the complete annotator layout with sidebar.

**`readme--corpus-home--with-chat`**: Add `docScreenshot` to the "renders landing view with chat bar and quick actions" test (line 304). Capture after chat bar and quick actions are visible.

### README Content Changes

- Replace the "Quick Look" section (4 images) with single hero screenshot + 5 feature sections
- Move GIFs to "See it in Action" section below features
- Collapse Architecture section with `<details>`
- Remove NLMatics reference image (acknowledgement can stay as text)
- Tighten Getting Started to just the docker commands
- Keep all documentation links

## Files Modified

1. `README.md` — Full rewrite
2. `frontend/tests/DocumentKnowledgeBase.ct.tsx` — Add docScreenshot call
3. `frontend/tests/CorpusHome.ct.tsx` — Add docScreenshot call
