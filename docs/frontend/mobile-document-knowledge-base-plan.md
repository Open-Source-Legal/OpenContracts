# Mobile DocumentKnowledgeBase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the DocumentKnowledgeBase a real mobile layout — a dedicated `MobileDocumentLayout` owner with a tabs + persistent-Ask-bar navigation model — replacing the uncoordinated per-component `isMobile` branches.

**Architecture:** `DocumentKnowledgeBase` keeps owning data + shared state and becomes a layout switch: `isMobile ? <MobileDocumentLayout/> : <DesktopDocumentLayout/>`. The current desktop render is extracted verbatim into `DesktopDocumentLayout`. `MobileDocumentLayout` composes the *same* surface components (PDF viewer, knowledge layer, chat, annotation feed) with mobile chrome. Desktop-only floating components stop rendering on mobile and their `isMobile` branches are deleted.

**Tech Stack:** React 18 + TypeScript, styled-components, Jotai, framer-motion, Playwright component tests.

**Reference spec:** `docs/frontend/mobile-document-knowledge-base-design.md`

---

## How to read this plan

This is an in-place restructure of a 1126-line component, not greenfield code. Two task styles are used:

- **New-component tasks** (Phase 2, and the tests) ship complete code — write it as shown.
- **Refactor/wire tasks** (Phases 1, 3, 4) give precise mechanics and the structural code, and call out exactly which existing prop interfaces to read before wiring. The executor reads the named file, confirms the interface, then wires per the structure shown. Inventing those interfaces blind would be wrong — read them.

Each phase ends green and shippable. Commit after every task.

**Conventions:**
- Mobile breakpoint: `width < 768` from `useWindowDimensions()` (already used in `DocumentKnowledgeBase.tsx`).
- Colors: `OS_LEGAL_COLORS` from `frontend/src/assets/configurations/osLegalStyles`.
- Run frontend commands from `frontend/`. Use `yarn run prettier --write` (project pins prettier 2.8.8 — never `npx prettier`).
- Component tests: `yarn test:ct --reporter=list` (the `--reporter=list` flag is mandatory or the run hangs).

---

## Phase 1 — Extract `DesktopDocumentLayout` (verbatim refactor; desktop unchanged)

Goal of this phase: zero behavior change. The current desktop render moves into its own component; `DocumentKnowledgeBase` renders it. The proof is the existing DKB test suite passing unchanged.

### Task 1: Record the desktop test baseline

**Files:** none (measurement only)

- [ ] **Step 1: List the existing DKB component tests**

Run: `cd frontend && ls tests/ | grep -i -E "knowledge|document"`
Also: `ls src/components/knowledge_base/document/__tests__/`

- [ ] **Step 2: Run the existing DKB component tests and record the result**

Run: `cd frontend && yarn test:ct --reporter=list -g "DocumentKnowledgeBase"`
Expected: a pass/fail count. Record the exact passing count in the task notes — this is the baseline Phase 1 must reproduce. If any test is already failing, note it as pre-existing (do not fix here).

- [ ] **Step 3: Commit nothing — baseline recorded in notes**

### Task 2: Create `DesktopDocumentLayout` and move the desktop render into it

**Files:**
- Create: `frontend/src/components/knowledge_base/document/layouts/DesktopDocumentLayout.tsx`
- Modify: `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`

- [ ] **Step 1: Read the current render section**

Read `DocumentKnowledgeBase.tsx` in full. Identify the JSX returned for the loaded state — it begins at the `<FullScreenModal>` wrapper and contains `<HeaderBar>`, `<ContentArea>`, `<MainContentArea>`, `mainLayerContent`, the `Floating*` components, `<SlidingPanel>` with `MobileSidebarTabs`/`DesktopSidebarTabs`/`RightPanelContent`, and `<DocumentModals>`. Note every prop/state/handler that JSX references.

- [ ] **Step 2: Create the new file with a props interface that passes everything the moved JSX needs**

Create `layouts/DesktopDocumentLayout.tsx`. Define `DesktopDocumentLayoutProps` listing — explicitly, one field per referenced value — every state value, setter, handler, and derived value the desktop JSX uses (e.g. `activeLayer`, `setActiveLayer`, `showRightPanel`, `setShowRightPanel`, `sidebarViewMode`, `setSidebarViewMode`, `zoomLevel`, `mainLayerContent`, `floatingControlsState`, `metadata`, `documentId`, `corpusId`, `readOnly`, … — derive the full list from Step 1, do not abbreviate). Move the desktop JSX verbatim into this component's `return`. Change nothing except replacing local identifiers with `props.` access.

- [ ] **Step 3: In `DocumentKnowledgeBase.tsx`, replace the moved JSX with `<DesktopDocumentLayout … />`**

Keep ALL hooks, state, data loading, effects, and derived values (`mainLayerContent`, `floatingControlsState`, the zoom manager, etc.) in `DocumentKnowledgeBase`. Replace only the returned desktop JSX with `<DesktopDocumentLayout />`, passing every prop the interface declares. Add the import.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && yarn tsc --noEmit`
Expected: no errors. Fix any missing/renamed prop until clean.

- [ ] **Step 5: Run the DKB test suite — must equal the Task 1 baseline**

Run: `cd frontend && yarn test:ct --reporter=list -g "DocumentKnowledgeBase"`
Expected: identical pass count to Task 1 Step 2. If any test newly fails, a prop was dropped or renamed in the move — diff against the baseline and fix. Do not proceed until equal.

- [ ] **Step 6: Format, then commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/DocumentKnowledgeBase.tsx src/components/knowledge_base/document/layouts/DesktopDocumentLayout.tsx
git add src/components/knowledge_base/document/DocumentKnowledgeBase.tsx src/components/knowledge_base/document/layouts/DesktopDocumentLayout.tsx
git commit -m "Extract DesktopDocumentLayout from DocumentKnowledgeBase (no behavior change)"
```

---

## Phase 2 — Mobile chrome primitives (new components, TDD)

Four small presentational components. Each is independent and fully tested before the next.

### Task 3: `MobileSheet` — generic full-height slide-up panel

**Files:**
- Create: `frontend/src/components/knowledge_base/document/layouts/mobile/MobileSheet.tsx`
- Test: `frontend/tests/MobileSheet.ct.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/MobileSheet.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { MobileSheet } from "./MobileSheet.harness";

test("renders title and content when open", async ({ mount }) => {
  const c = await mount(
    <MobileSheet open title="Chat" onClose={() => {}}>
      <div>sheet-body</div>
    </MobileSheet>
  );
  await expect(c.getByText("Chat")).toBeVisible();
  await expect(c.getByText("sheet-body")).toBeVisible();
});

test("does not render content when closed", async ({ mount }) => {
  const c = await mount(
    <MobileSheet open={false} title="Chat" onClose={() => {}}>
      <div>sheet-body</div>
    </MobileSheet>
  );
  await expect(c.getByText("sheet-body")).toHaveCount(0);
});

test("close button fires onClose", async ({ mount }) => {
  let closed = false;
  const c = await mount(
    <MobileSheet open title="Chat" onClose={() => { closed = true; }}>
      <div>x</div>
    </MobileSheet>
  );
  await c.getByRole("button", { name: /close/i }).click();
  expect(closed).toBe(true);
});
```

Create the harness re-export `frontend/tests/MobileSheet.harness.tsx` containing only:
```tsx
export { MobileSheet } from "../src/components/knowledge_base/document/layouts/mobile/MobileSheet";
```
(Harness keeps the JSX-component import isolated — see CLAUDE.md pitfall #16: Playwright CT requires component imports in their own statement.)

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd frontend && yarn test:ct --reporter=list MobileSheet`
Expected: FAIL — module `MobileSheet` not found.

- [ ] **Step 3: Implement `MobileSheet`**

```tsx
// frontend/src/components/knowledge_base/document/layouts/mobile/MobileSheet.tsx
import React from "react";
import styled from "styled-components";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export interface MobileSheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

const Scrim = styled(motion.div)`
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.32);
  z-index: 50;
`;

const Panel = styled(motion.div)`
  position: absolute;
  inset: 0;
  z-index: 51;
  display: flex;
  flex-direction: column;
  background: ${OS_LEGAL_COLORS.background};
`;

const Header = styled.div`
  flex-shrink: 0;
  height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
`;

const Title = styled.div`
  flex: 1;
  font-size: 15px;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const CloseButton = styled.button`
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
`;

const Body = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
`;

/** Full-height slide-up panel. One open/close animation, one close action.
 *  Deliberately not a draggable multi-snap sheet. */
export const MobileSheet: React.FC<MobileSheetProps> = ({
  open,
  title,
  onClose,
  children,
}) => (
  <AnimatePresence>
    {open && (
      <>
        <Scrim
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        />
        <Panel
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "tween", duration: 0.22 }}
        >
          <Header>
            <Title>{title}</Title>
            <CloseButton aria-label="Close" onClick={onClose}>
              <X size={18} />
            </CloseButton>
          </Header>
          <Body>{children}</Body>
        </Panel>
      </>
    )}
  </AnimatePresence>
);
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd frontend && yarn test:ct --reporter=list MobileSheet`
Expected: 3 passed.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/mobile/MobileSheet.tsx tests/MobileSheet.ct.tsx tests/MobileSheet.harness.tsx
git add src/components/knowledge_base/document/layouts/mobile/MobileSheet.tsx tests/MobileSheet.ct.tsx tests/MobileSheet.harness.tsx
git commit -m "Add MobileSheet slide-up panel primitive"
```

### Task 4: `MobileTabBar` — bottom 4-tab navigation

**Files:**
- Create: `frontend/src/components/knowledge_base/document/layouts/mobile/MobileTabBar.tsx`
- Test: `frontend/tests/MobileTabBar.ct.tsx` + `frontend/tests/MobileTabBar.harness.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/MobileTabBar.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { MobileTabBar } from "./MobileTabBar.harness";

const TABS = ["document", "summary", "annotations", "more"] as const;

test("renders all four tabs", async ({ mount }) => {
  const c = await mount(<MobileTabBar active="document" onSelect={() => {}} />);
  for (const t of ["Document", "Summary", "Annotations", "More"]) {
    await expect(c.getByRole("tab", { name: t })).toBeVisible();
  }
});

test("marks the active tab", async ({ mount }) => {
  const c = await mount(<MobileTabBar active="summary" onSelect={() => {}} />);
  await expect(c.getByRole("tab", { name: "Summary" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
});

test("clicking a tab fires onSelect with its id", async ({ mount }) => {
  let picked = "";
  const c = await mount(
    <MobileTabBar active="document" onSelect={(id) => { picked = id; }} />
  );
  await c.getByRole("tab", { name: "Annotations" }).click();
  expect(picked).toBe("annotations");
});
```

Harness `frontend/tests/MobileTabBar.harness.tsx`:
```tsx
export { MobileTabBar } from "../src/components/knowledge_base/document/layouts/mobile/MobileTabBar";
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd frontend && yarn test:ct --reporter=list MobileTabBar`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `MobileTabBar`**

```tsx
// frontend/src/components/knowledge_base/document/layouts/mobile/MobileTabBar.tsx
import React from "react";
import styled from "styled-components";
import { FileText, BookOpen, Bookmark, MoreHorizontal } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export type MobileTabId = "document" | "summary" | "annotations" | "more";

export interface MobileTabBarProps {
  active: MobileTabId;
  onSelect: (id: MobileTabId) => void;
}

const TABS: { id: MobileTabId; label: string; Icon: React.FC<any> }[] = [
  { id: "document", label: "Document", Icon: FileText },
  { id: "summary", label: "Summary", Icon: BookOpen },
  { id: "annotations", label: "Annotations", Icon: Bookmark },
  { id: "more", label: "More", Icon: MoreHorizontal },
];

const Bar = styled.div`
  flex-shrink: 0;
  height: 56px;
  display: flex;
  background: white;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
`;

const Tab = styled.button<{ $active: boolean }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 11px;
  font-weight: 500;
  color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textSecondary};
`;

export const MobileTabBar: React.FC<MobileTabBarProps> = ({
  active,
  onSelect,
}) => (
  <Bar role="tablist">
    {TABS.map(({ id, label, Icon }) => (
      <Tab
        key={id}
        role="tab"
        aria-selected={active === id}
        aria-label={label}
        $active={active === id}
        onClick={() => onSelect(id)}
      >
        <Icon size={20} />
        {label}
      </Tab>
    ))}
  </Bar>
);
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd frontend && yarn test:ct --reporter=list MobileTabBar`
Expected: 3 passed.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/mobile/MobileTabBar.tsx tests/MobileTabBar.ct.tsx tests/MobileTabBar.harness.tsx
git add src/components/knowledge_base/document/layouts/mobile/MobileTabBar.tsx tests/MobileTabBar.ct.tsx tests/MobileTabBar.harness.tsx
git commit -m "Add MobileTabBar bottom navigation primitive"
```

### Task 5: `MobileAskBar` — persistent ask input

**Files:**
- Create: `frontend/src/components/knowledge_base/document/layouts/mobile/MobileAskBar.tsx`
- Test: `frontend/tests/MobileAskBar.ct.tsx` + harness

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/MobileAskBar.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { MobileAskBar } from "./MobileAskBar.harness";

test("renders the prompt", async ({ mount }) => {
  const c = await mount(<MobileAskBar onActivate={() => {}} onSubmit={() => {}} />);
  await expect(c.getByPlaceholder(/ask anything/i)).toBeVisible();
});

test("focusing the input fires onActivate", async ({ mount }) => {
  let activated = false;
  const c = await mount(
    <MobileAskBar onActivate={() => { activated = true; }} onSubmit={() => {}} />
  );
  await c.getByPlaceholder(/ask anything/i).focus();
  expect(activated).toBe(true);
});

test("submitting non-empty text fires onSubmit with the text", async ({ mount }) => {
  let sent = "";
  const c = await mount(
    <MobileAskBar onActivate={() => {}} onSubmit={(t) => { sent = t; }} />
  );
  const input = c.getByPlaceholder(/ask anything/i);
  await input.fill("what year?");
  await input.press("Enter");
  expect(sent).toBe("what year?");
});
```

Harness `frontend/tests/MobileAskBar.harness.tsx`:
```tsx
export { MobileAskBar } from "../src/components/knowledge_base/document/layouts/mobile/MobileAskBar";
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd frontend && yarn test:ct --reporter=list MobileAskBar`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `MobileAskBar`**

```tsx
// frontend/src/components/knowledge_base/document/layouts/mobile/MobileAskBar.tsx
import React, { useState } from "react";
import styled from "styled-components";
import { Search, Send } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export interface MobileAskBarProps {
  /** Fired when the user focuses the bar — the layout opens the Chat sheet. */
  onActivate: () => void;
  /** Fired when the user submits non-empty text. */
  onSubmit: (text: string) => void;
}

const Bar = styled.div`
  flex-shrink: 0;
  margin: 8px 12px;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px 0 12px;
  border: 1.5px solid ${OS_LEGAL_COLORS.accent};
  border-radius: 20px;
  background: ${OS_LEGAL_COLORS.successSurface};
`;

const Input = styled.input`
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textPrimary};
  outline: none;
  &::placeholder {
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const SendButton = styled.button`
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
`;

export const MobileAskBar: React.FC<MobileAskBarProps> = ({
  onActivate,
  onSubmit,
}) => {
  const [text, setText] = useState("");
  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setText("");
  };
  return (
    <Bar>
      <Search size={16} color={OS_LEGAL_COLORS.accent} />
      <Input
        placeholder="Ask anything about this document…"
        value={text}
        onFocus={onActivate}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
      />
      <SendButton aria-label="Send" onClick={submit}>
        <Send size={15} />
      </SendButton>
    </Bar>
  );
};
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd frontend && yarn test:ct --reporter=list MobileAskBar`
Expected: 3 passed.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/mobile/MobileAskBar.tsx tests/MobileAskBar.ct.tsx tests/MobileAskBar.harness.tsx
git add src/components/knowledge_base/document/layouts/mobile/MobileAskBar.tsx tests/MobileAskBar.ct.tsx tests/MobileAskBar.harness.tsx
git commit -m "Add MobileAskBar persistent ask input primitive"
```

### Task 6: `MobileDocToolbar` — in-document toolbar (Sections / Find / zoom)

**Files:**
- Create: `frontend/src/components/knowledge_base/document/layouts/mobile/MobileDocToolbar.tsx`
- Test: `frontend/tests/MobileDocToolbar.ct.tsx` + harness

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/MobileDocToolbar.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { MobileDocToolbar } from "./MobileDocToolbar.harness";

test("renders the three controls", async ({ mount }) => {
  const c = await mount(
    <MobileDocToolbar
      zoomPercent={100}
      onSections={() => {}}
      onFind={() => {}}
      onFitWidth={() => {}}
    />
  );
  await expect(c.getByRole("button", { name: /sections/i })).toBeVisible();
  await expect(c.getByRole("button", { name: /find/i })).toBeVisible();
  await expect(c.getByRole("button", { name: /fit width/i })).toBeVisible();
});

test("buttons fire their callbacks", async ({ mount }) => {
  const hits: string[] = [];
  const c = await mount(
    <MobileDocToolbar
      zoomPercent={100}
      onSections={() => hits.push("s")}
      onFind={() => hits.push("f")}
      onFitWidth={() => hits.push("z")}
    />
  );
  await c.getByRole("button", { name: /sections/i }).click();
  await c.getByRole("button", { name: /find/i }).click();
  await c.getByRole("button", { name: /fit width/i }).click();
  expect(hits).toEqual(["s", "f", "z"]);
});
```

Harness `frontend/tests/MobileDocToolbar.harness.tsx`:
```tsx
export { MobileDocToolbar } from "../src/components/knowledge_base/document/layouts/mobile/MobileDocToolbar";
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `cd frontend && yarn test:ct --reporter=list MobileDocToolbar`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `MobileDocToolbar`**

```tsx
// frontend/src/components/knowledge_base/document/layouts/mobile/MobileDocToolbar.tsx
import React from "react";
import styled from "styled-components";
import { List, Search, Maximize2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export interface MobileDocToolbarProps {
  zoomPercent: number;
  onSections: () => void;
  onFind: () => void;
  onFitWidth: () => void;
}

const Bar = styled.div`
  flex-shrink: 0;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  background: ${OS_LEGAL_COLORS.background};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const Chip = styled.button`
  height: 24px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  background: white;
  font-size: 11px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
`;

const Spacer = styled.div`
  flex: 1;
`;

export const MobileDocToolbar: React.FC<MobileDocToolbarProps> = ({
  zoomPercent,
  onSections,
  onFind,
  onFitWidth,
}) => (
  <Bar>
    <Chip aria-label="Sections" onClick={onSections}>
      <List size={13} /> Sections
    </Chip>
    <Chip aria-label="Find" onClick={onFind}>
      <Search size={13} /> Find
    </Chip>
    <Spacer />
    <Chip aria-label="Fit width" onClick={onFitWidth}>
      <Maximize2 size={13} /> {Math.round(zoomPercent)}%
    </Chip>
  </Bar>
);
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd frontend && yarn test:ct --reporter=list MobileDocToolbar`
Expected: 2 passed.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/mobile/MobileDocToolbar.tsx tests/MobileDocToolbar.ct.tsx tests/MobileDocToolbar.harness.tsx
git add src/components/knowledge_base/document/layouts/mobile/MobileDocToolbar.tsx tests/MobileDocToolbar.ct.tsx tests/MobileDocToolbar.harness.tsx
git commit -m "Add MobileDocToolbar in-document toolbar primitive"
```

---

## Phase 3 — `MobileDocumentLayout` (compose the surfaces)

This phase builds the mobile layout owner and wires the existing surface components into it. Every wiring task names the existing component to read for its prop interface before wiring.

### Task 7: `MobileDocumentLayout` skeleton — chrome + tab state

**Files:**
- Create: `frontend/src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx`
- Test: `frontend/tests/MobileDocumentLayout.ct.tsx` + harness

- [ ] **Step 1: Read the desktop layout props**

Read `layouts/DesktopDocumentLayout.tsx` (created in Task 2). `MobileDocumentLayout` receives the **same props interface** — reuse `DesktopDocumentLayoutProps` (export it from that file; import it here). Both layouts are alternative presentations of identical data/state.

- [ ] **Step 2: Write the failing test**

```tsx
// frontend/tests/MobileDocumentLayout.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { MobileLayoutHarness } from "./MobileDocumentLayout.harness";

test.use({ viewport: { width: 390, height: 844 } });

test("starts on the Document tab with chrome present", async ({ mount }) => {
  const c = await mount(<MobileLayoutHarness />);
  await expect(c.getByRole("tab", { name: "Document" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(c.getByPlaceholder(/ask anything/i)).toBeVisible();
});

test("selecting the Summary tab swaps the surface", async ({ mount }) => {
  const c = await mount(<MobileLayoutHarness />);
  await c.getByRole("tab", { name: "Summary" }).click();
  await expect(c.getByRole("tab", { name: "Summary" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(c.getByTestId("mobile-surface-summary")).toBeVisible();
});
```

Harness `frontend/tests/MobileDocumentLayout.harness.tsx` — a wrapper supplying stub props (a real harness is built in Task 12's integration test; here use placeholder surface nodes passed as props so the skeleton is testable in isolation). Export it as `MobileLayoutHarness`.

- [ ] **Step 3: Run the test, verify it fails**

Run: `cd frontend && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement the skeleton**

Create `MobileDocumentLayout.tsx`. It renders, top to bottom: `HeaderBar` (reuse the existing `document_kb/HeaderBar`), a surface area that switches on a local `activeTab` state (`MobileTabId`), the `MobileAskBar`, and `MobileTabBar`. The surface area renders one of four nodes; for this task they may be the props-provided placeholders. Each surface wrapper gets `data-testid={`mobile-surface-${tab}`}`. The `more` tab toggles a `MobileSheet`. Map `activeTab` → the shared state setters from props per the spec table:

| activeTab | effect |
|-----------|--------|
| `document` | `props.setActiveLayer("document")` |
| `summary` | `props.setActiveLayer("knowledge")` |
| `annotations` | `props.setActiveLayer("document"); props.setSidebarViewMode("feed")` |
| `more` | open the More sheet |

Outer container: `display:flex; flex-direction:column; height:100%` so chrome is fixed and only the surface scrolls.

- [ ] **Step 5: Run the test, verify it passes**

Run: `cd frontend && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: 2 passed.

- [ ] **Step 6: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx tests/MobileDocumentLayout.ct.tsx tests/MobileDocumentLayout.harness.tsx
git add src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx tests/MobileDocumentLayout.ct.tsx tests/MobileDocumentLayout.harness.tsx
git commit -m "Add MobileDocumentLayout skeleton with tab navigation"
```

### Task 8: Wire the Document surface (PDF viewer + toolbar, fit-to-width)

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx`

- [ ] **Step 1: Read the viewer interface**

Read `document_kb/DocumentViewer.tsx` and the `mainLayerContent` construction in `DocumentKnowledgeBase.tsx` (the `activeLayer === "knowledge" ? <UnifiedKnowledgeLayer/> : <div id="document-layer">{viewerContent}</div>` block). Note the props `DocumentViewer` requires.

- [ ] **Step 2: Render the document surface**

In `MobileDocumentLayout`, the `document` tab surface renders `MobileDocToolbar` above the same `viewerContent` the desktop layout uses (passed in via props — add `viewerContent: React.ReactNode` to the shared props interface if not already present). Wire `MobileDocToolbar`:
- `zoomPercent={props.zoomLevel * 100}`
- `onFitWidth` → call the fit-to-width path. Read `document_kb/useZoomManager.ts` for the existing fit/auto-zoom function; if `autoZoomEnabled` already yields fit-to-width, `onFitWidth` toggles it on. On mobile, default the initial zoom to fit-to-width by enabling auto-zoom on mount (see Task 11 for the verification of readable default).
- `onSections` → opens a sheet with the structural section index (read `useStructuralAnnotations` from `document_kb/useStructuralAnnotations` for the section list shape).
- `onFind` → opens the in-document search; read `useTextSearch` / `useSearchText` usage in `DocumentKnowledgeBase.tsx`.

- [ ] **Step 3: Typecheck and run mobile-layout tests**

Run: `cd frontend && yarn tsc --noEmit && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: tsc clean; tests pass.

- [ ] **Step 4: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git add src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git commit -m "Wire Document surface into MobileDocumentLayout"
```

### Task 9: Wire the Summary surface

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx`

- [ ] **Step 1: Read the knowledge layer interface**

Read `layers/UnifiedKnowledgeLayer.tsx` — note its required props (`documentId`, `corpusId`, `metadata`, `parentLoading`, `readOnly` are used in `DocumentKnowledgeBase.tsx`).

- [ ] **Step 2: Render the summary surface**

The `summary` tab surface renders `<UnifiedKnowledgeLayer documentId={props.documentId} corpusId={props.corpusId} metadata={props.metadata} parentLoading={props.loading} readOnly={props.readOnly} />` inside the `data-testid="mobile-surface-summary"` wrapper, full-screen scroll. Selecting the tab also calls `props.setActiveLayer("knowledge")`.

- [ ] **Step 3: Typecheck and test**

Run: `cd frontend && yarn tsc --noEmit && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: clean + pass.

- [ ] **Step 4: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git add src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git commit -m "Wire Summary surface into MobileDocumentLayout"
```

### Task 10: Wire the Annotations surface + annotation detail sheet

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx`

- [ ] **Step 1: Read the feed + detail interfaces**

Read `document_kb/RightPanelContent.tsx` — it already renders the annotation feed for `sidebarViewMode === "feed"`. Read how an annotation row's detail (comment thread + vote + approve) is rendered today (in `right_tray/` or the unified feed). The annotation detail sheet reuses that existing detail component — identify it and its props.

- [ ] **Step 2: Render the Annotations surface**

The `annotations` tab surface renders the feed (reuse `RightPanelContent` with `sidebarViewMode="feed"`, or the underlying feed list component it delegates to) full-screen inside `data-testid="mobile-surface-annotations"`. Selecting the tab calls `props.setSidebarViewMode("feed")`.

- [ ] **Step 3: Wire the annotation detail sheet**

When `props.selectedAnnotation` is set, render the existing annotation-detail component inside a `MobileSheet` titled "Annotation". Opening paths: tapping a feed row (already sets `selectedAnnotation`) and tapping a highlight in the Document tab (the viewer already sets it). Closing the sheet clears `props.selectedAnnotation`. Verify the detail component exposes vote / approve / comment — those are existing capabilities; no new logic.

- [ ] **Step 4: Typecheck and test**

Run: `cd frontend && yarn tsc --noEmit && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: clean + pass.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git add src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git commit -m "Wire Annotations surface and detail sheet into MobileDocumentLayout"
```

### Task 11: Wire the Chat sheet

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx`

- [ ] **Step 1: Read the chat interface**

Read `RightPanelContent.tsx` for how `sidebarViewMode === "chat"` renders chat, and `right_tray/ChatTray.tsx`. Note how `pendingChatMessage` is consumed (it exists as DKB state passed to `RightPanelContent`).

- [ ] **Step 2: Wire the Ask bar to a Chat sheet**

Add local `chatOpen` state. `MobileAskBar`:
- `onActivate` → `setChatOpen(true)`
- `onSubmit(text)` → `props.setPendingChatMessage(text); props.setSidebarViewMode("chat"); setChatOpen(true)`

Render the chat content (the same component `RightPanelContent` uses for `"chat"`) inside a `MobileSheet open={chatOpen} title="Chat"`. Closing sets `chatOpen=false`. A source-citation click inside chat should call `setChatOpen(false)` and switch `activeTab` to `document` — wire via the existing chat-source handler (`useChatSourceState`).

- [ ] **Step 3: Typecheck and test**

Run: `cd frontend && yarn tsc --noEmit && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: clean + pass.

- [ ] **Step 4: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git add src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git commit -m "Wire Chat sheet into MobileDocumentLayout"
```

### Task 12: Wire the More sheet

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx`

- [ ] **Step 1: Render the More sheet**

The `more` tab opens a `MobileSheet` titled "More" containing a simple list: **Discussions**, **Notes**, **Document info & versions**. Tapping Discussions → `props.setSidebarViewMode("discussion")` and render that surface (reuse `RightPanelContent`'s discussion view) inside the sheet. Tapping Notes → `props.setSidebarViewMode("notes")` likewise. Confirm the `SidebarViewMode` union (imported from `./unified_feed`) includes these values; if a value differs, use the actual union member.

- [ ] **Step 2: Typecheck and test**

Run: `cd frontend && yarn tsc --noEmit && yarn test:ct --reporter=list MobileDocumentLayout`
Expected: clean + pass.

- [ ] **Step 3: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git add src/components/knowledge_base/document/layouts/MobileDocumentLayout.tsx
git commit -m "Wire More sheet into MobileDocumentLayout"
```

### Task 13: Switch `DocumentKnowledgeBase` to render the mobile layout when `isMobile`

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/DocumentKnowledgeBase.tsx`

- [ ] **Step 1: Add the layout switch**

In `DocumentKnowledgeBase.tsx`, where it currently renders `<DesktopDocumentLayout {...layoutProps} />`, change to:
```tsx
{isMobile ? (
  <MobileDocumentLayout {...layoutProps} />
) : (
  <DesktopDocumentLayout {...layoutProps} />
)}
```
`isMobile` already exists (`width < 768`). `layoutProps` is the same object both layouts consume. Add the `MobileDocumentLayout` import.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && yarn tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Manual smoke — desktop and mobile**

Start the app (`docker compose -f local.yml up -d django`; `cd frontend && yarn start`). Open a processed PDF document. At a desktop viewport: unchanged. Narrow the window below 768px: the mobile layout renders — tab bar, Ask bar, no floating overlays over the document.

- [ ] **Step 4: Run the full DKB suite — desktop baseline must still hold**

Run: `cd frontend && yarn test:ct --reporter=list -g "DocumentKnowledgeBase"`
Expected: still equals the Task 1 baseline.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/DocumentKnowledgeBase.tsx
git add src/components/knowledge_base/document/DocumentKnowledgeBase.tsx
git commit -m "Render MobileDocumentLayout in DocumentKnowledgeBase when isMobile"
```

---

## Phase 4 — Remove the now-dead `isMobile` branches

The floating components are desktop-only now. Delete their mobile code paths.

### Task 14: Delete `isMobile` branches from the floating components

**Files:**
- Modify: `frontend/src/components/knowledge_base/document/FloatingDocumentControls.tsx`
- Modify: `frontend/src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview.tsx`
- Modify: `frontend/src/components/knowledge_base/document/document_kb/SidebarTabs.tsx` (remove `MobileSidebarTabs` if now unused)
- Modify: `frontend/src/components/knowledge_base/document/layouts/DesktopDocumentLayout.tsx` (drop `MobileSidebarTabs` usage)

- [ ] **Step 1: Confirm these render only on the desktop path**

Grep each component's usages: `cd frontend && grep -rn "FloatingDocumentControls\|FloatingSummaryPreview\|MobileSidebarTabs" src/`. Confirm every usage is inside `DesktopDocumentLayout` (or other desktop-only code), not `MobileDocumentLayout`.

- [ ] **Step 2: Remove the mobile branches**

In `FloatingDocumentControls.tsx`: delete the `if (isMobile) { … }` speed-dial block and the `isMobile` prop. In `FloatingSummaryPreview.tsx`: delete the `if (isMobile)` branch and the `isMobile` prop. Remove `MobileSidebarTabs` (its export and definition) from `SidebarTabs.tsx` if Step 1 showed it unused. Remove the now-unused `isMobile` props passed from `DesktopDocumentLayout.tsx`. Delete any imports left dangling.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && yarn tsc --noEmit`
Expected: clean — no unused-variable or missing-prop errors.

- [ ] **Step 4: Run the DKB suite — baseline still holds**

Run: `cd frontend && yarn test:ct --reporter=list -g "DocumentKnowledgeBase"`
Expected: equals the Task 1 baseline.

- [ ] **Step 5: Format and commit**

```bash
cd frontend && yarn run prettier --write src/components/knowledge_base/document/FloatingDocumentControls.tsx src/components/knowledge_base/document/floating_summary_preview/FloatingSummaryPreview.tsx src/components/knowledge_base/document/document_kb/SidebarTabs.tsx src/components/knowledge_base/document/layouts/DesktopDocumentLayout.tsx
git add -A
git commit -m "Delete dead isMobile branches from desktop-only floating components"
```

---

## Phase 5 — Mobile test suite & verification

### Task 15: Mobile integration component tests

**Files:**
- Create: `frontend/tests/MobileDocumentKnowledgeBase.ct.tsx`
- Create: `frontend/tests/MobileDocumentKnowledgeBase.harness.tsx`

- [ ] **Step 1: Build the harness**

Read `tests/` for the existing `DocumentKnowledgeBaseTestWrapper` (referenced in CLAUDE.md). Create `MobileDocumentKnowledgeBase.harness.tsx` that re-exports a wrapper mounting `DocumentKnowledgeBase` through `DocumentKnowledgeBaseTestWrapper` with the standard GraphQL mocks. Keep the component import in its own statement (CLAUDE.md CT pitfall #16).

- [ ] **Step 2: Write the integration tests**

```tsx
// frontend/tests/MobileDocumentKnowledgeBase.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import { MobileDKB } from "./MobileDocumentKnowledgeBase.harness";

test.use({ viewport: { width: 390, height: 844 } });

test("renders the mobile layout, not the desktop floating UI", async ({ mount }) => {
  const c = await mount(<MobileDKB />);
  await expect(c.getByRole("tablist")).toBeVisible();
  await expect(c.getByPlaceholder(/ask anything/i)).toBeVisible();
  // absence assertions — Tier-3 / desktop-only must not render
  await expect(c.getByTestId("settings-button")).toHaveCount(0);
  await expect(c.getByTestId("summary-button")).toHaveCount(0);
});

test("no horizontal overflow at 390px", async ({ mount, page }) => {
  await mount(<MobileDKB />);
  await page.waitForTimeout(20000); // PDF render
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("Ask bar opens the Chat sheet", async ({ mount }) => {
  const c = await mount(<MobileDKB />);
  await c.getByPlaceholder(/ask anything/i).click();
  await expect(c.getByRole("button", { name: /close/i })).toBeVisible();
});

test("tapping an annotation row opens the detail sheet", async ({ mount }) => {
  const c = await mount(<MobileDKB />);
  await c.getByRole("tab", { name: "Annotations" }).click();
  const firstRow = c.getByTestId("annotation-row").first();
  await firstRow.click();
  await expect(c.getByText("Annotation")).toBeVisible();
});
```

If a `data-testid` referenced above (`annotation-row`, `settings-button`, `summary-button`) does not match the real DOM, read the component and use the actual testid/role. Add `data-testid="annotation-row"` to the feed row component if none exists.

- [ ] **Step 3: Run the tests**

Run: `cd frontend && yarn test:ct --reporter=list MobileDocumentKnowledgeBase`
Expected: 4 passed. Fix wiring until green.

- [ ] **Step 4: Format and commit**

```bash
cd frontend && yarn run prettier --write tests/MobileDocumentKnowledgeBase.ct.tsx tests/MobileDocumentKnowledgeBase.harness.tsx
git add tests/MobileDocumentKnowledgeBase.ct.tsx tests/MobileDocumentKnowledgeBase.harness.tsx
git commit -m "Add mobile DocumentKnowledgeBase integration tests"
```

### Task 16: Layout-audit re-run + documentation screenshots

**Files:**
- Modify: `frontend/tests/MobileDocumentKnowledgeBase.ct.tsx` (add screenshot capture)

- [ ] **Step 1: Add `docScreenshot` captures**

Import `docScreenshot` from `./utils/docScreenshot`. After each surface reaches its visual state, capture: `await docScreenshot(page, "knowledge-base--mobile--document")`, `"…--mobile--summary"`, `"…--mobile--annotations"`, `"…--mobile--chat-sheet"`. Place each call after the assertions confirming that state.

- [ ] **Step 2: Run and confirm screenshots are produced**

Run: `cd frontend && yarn test:ct --reporter=list MobileDocumentKnowledgeBase`
Expected: pass; PNGs appear under `docs/assets/images/screenshots/auto/`.

- [ ] **Step 3: Commit**

```bash
cd frontend && yarn run prettier --write tests/MobileDocumentKnowledgeBase.ct.tsx
git add tests/MobileDocumentKnowledgeBase.ct.tsx
git commit -m "Capture mobile DocumentKnowledgeBase documentation screenshots"
```

### Task 17: Final verification gate

**Files:** none (verification only)

- [ ] **Step 1: Typecheck and lint**

Run: `cd frontend && yarn tsc --noEmit && yarn lint`
Expected: both clean.

- [ ] **Step 2: Full DKB suite — desktop baseline + new mobile tests**

Run: `cd frontend && yarn test:ct --reporter=list -g "DocumentKnowledgeBase"`
Expected: the Task 1 desktop baseline count, unchanged, plus the new mobile tests passing.

- [ ] **Step 3: Manual mobile drive**

With the app running, open a processed PDF at a 390px viewport. Confirm against the spec success criteria: document readable on load (fit-to-width); zero floating overlays over the document; Document/Summary/Chat/Annotations reachable in one tap; Discussions/Notes in two; no horizontal scroll.

- [ ] **Step 4: Update the changelog**

Add an entry to `CHANGELOG.md` under `[Unreleased]` → `### Changed`: the DocumentKnowledgeBase now has a dedicated mobile layout (`MobileDocumentLayout`); note the new files and that desktop is unchanged.

```bash
git add CHANGELOG.md
git commit -m "Update changelog for mobile DocumentKnowledgeBase layout"
```

---

## Phase 6 — Visual inspection & iterate to perfection

### Task 18: Re-run the mobile visual audit and iterate until the surfaces look right

**Files:** none directly — this task drives the running app, inspects screenshots, and dispatches fixes.

- [ ] **Step 1: Bring up the app**

Backend: `docker compose -f local.yml up -d django`. Frontend: `cd frontend && yarn start` (Vite on :5173).

- [ ] **Step 2: Drive the real mobile DocumentKnowledgeBase at 390px and screenshot every surface**

Use a headless Playwright drive at a 390×844 viewport (the same technique as the original audit — intercept `**/graphql**`, proxy each POST server-side with a Django `sessionid` + CSRF token; see `CLAUDE.md` → "Authenticated Playwright Testing"). Open a processed PDF document and capture: the Document surface (on load — verify fit-to-width), the Summary tab, the Annotations tab, the annotation detail sheet, the Chat sheet, the More sheet, the Sections sheet, the Find sheet. Also measure: horizontal overflow (`scrollWidth − clientWidth` must be ≤ 1) and console errors.

- [ ] **Step 3: Visually inspect each screenshot**

Look at every captured screenshot for crowding, clipping, overflow, awkward spacing, overlapping controls, unreadable text, mis-aligned chrome — the same criteria as the original audit. Judge it as a user would.

- [ ] **Step 4: Iterate to perfection**

For each genuine visual defect found, dispatch a focused fix (a small implementer subagent or a direct edit), re-run Step 2, and re-inspect. Repeat until the surfaces are clean: document readable on load, no overflow, no overlapping/clipped controls, chrome aligned, every surface reachable and legible. Commit each fix.

- [ ] **Step 5: Final confirmation**

Re-run `cd frontend && yarn tsc --noEmit && yarn lint` and `yarn test:ct --reporter=list -g "DocumentKnowledgeBase"` — all green, desktop baseline still 66/0. Commit any remaining changes.

---

## Self-review notes

- **Spec coverage:** navigation model (Tasks 3–7), four surfaces (Tasks 8–11), More sheet (Task 12), annotation detail sheet / review flow (Task 10), architecture / layout owner + extraction (Tasks 2, 7, 13), state mapping (Task 7 table), `isMobile`-branch deletion (Task 14), desktop regression gate (Tasks 1, 13, 14, 17), mobile tests + absence assertions + audit re-run (Tasks 15–16). Out-of-scope items (annotation authoring, Analyses/Extracts, tablet) are honored by never wiring them into `MobileDocumentLayout`.
- **Phasing:** each phase ends green — Phase 1 ships a pure refactor; Phases 2–3 add the mobile layout; Phase 4 is dead-code removal; Phase 5 is verification.
- **Interface reads:** refactor/wire tasks (2, 8–14) explicitly name the existing file whose prop interface must be read before wiring, rather than inventing signatures.
