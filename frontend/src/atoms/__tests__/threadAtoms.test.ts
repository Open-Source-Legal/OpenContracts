import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createStore } from "jotai";
import {
  threadSortAtom,
  threadFiltersAtom,
  selectedMessageIdAtom,
  replyingToMessageIdAtom,
  threadContextSidebarExpandedAtom,
} from "../threadAtoms";

describe("threadAtoms — primitive atoms", () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    // Clear persisted state before each test run.
    localStorage.clear();
    store = createStore();
  });

  describe("threadSortAtom", () => {
    it("defaults to 'pinned'", () => {
      expect(store.get(threadSortAtom)).toBe("pinned");
    });

    it("accepts all known sort options", () => {
      for (const option of ["newest", "active", "upvoted", "pinned"] as const) {
        store.set(threadSortAtom, option);
        expect(store.get(threadSortAtom)).toBe(option);
      }
    });
  });

  describe("threadFiltersAtom", () => {
    it("defaults to { showLocked: true, showDeleted: false }", () => {
      expect(store.get(threadFiltersAtom)).toEqual({
        showLocked: true,
        showDeleted: false,
      });
    });

    it("accepts updated filter shape", () => {
      store.set(threadFiltersAtom, { showLocked: false, showDeleted: true });
      expect(store.get(threadFiltersAtom)).toEqual({
        showLocked: false,
        showDeleted: true,
      });
    });
  });

  describe("selectedMessageIdAtom", () => {
    it("defaults to null and round-trips a string", () => {
      expect(store.get(selectedMessageIdAtom)).toBeNull();
      store.set(selectedMessageIdAtom, "msg-42");
      expect(store.get(selectedMessageIdAtom)).toBe("msg-42");
      store.set(selectedMessageIdAtom, null);
      expect(store.get(selectedMessageIdAtom)).toBeNull();
    });
  });

  describe("replyingToMessageIdAtom", () => {
    it("defaults to null and round-trips a string", () => {
      expect(store.get(replyingToMessageIdAtom)).toBeNull();
      store.set(replyingToMessageIdAtom, "parent-msg");
      expect(store.get(replyingToMessageIdAtom)).toBe("parent-msg");
    });
  });

  describe("threadContextSidebarExpandedAtom", () => {
    it("defaults to true (expanded)", () => {
      expect(store.get(threadContextSidebarExpandedAtom)).toBe(true);
    });

    it("round-trips and persists to localStorage", () => {
      store.set(threadContextSidebarExpandedAtom, false);
      expect(store.get(threadContextSidebarExpandedAtom)).toBe(false);
      expect(localStorage.getItem("threadContextSidebarExpanded")).toBe(
        JSON.stringify(false)
      );
    });
  });
});

describe("threadAtoms — persistence hydration", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("threadContextSidebarExpandedAtom rehydrates from localStorage", async () => {
    localStorage.setItem("threadContextSidebarExpanded", JSON.stringify(false));
    const { threadContextSidebarExpandedAtom: freshAtom } = await import(
      "../threadAtoms"
    );
    const store = createStore();
    // atomWithStorage lazy-hydrates on subscribe (getOnInit defaults to false),
    // so subscribing forces a read from localStorage.
    const unsub = store.sub(freshAtom, () => {});
    expect(store.get(freshAtom)).toBe(false);
    unsub();
  });
});
