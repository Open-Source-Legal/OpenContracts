import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { createStore } from "jotai";
import {
  selectedFolderIdAtom,
  folderCorpusIdAtom,
  folderListAtom,
  corpusPermissionsAtom,
  folderTreeAtom,
  folderBreadcrumbAtom,
  folderMapAtom,
  expandedFolderIdsAtom,
  showCreateFolderModalAtom,
  showEditFolderModalAtom,
  showMoveFolderModalAtom,
  showDeleteFolderModalAtom,
  activeFolderModalIdAtom,
  createFolderParentIdAtom,
  folderSearchQueryAtom,
  draggingFolderIdAtom,
  dropTargetFolderIdAtom,
  canCreateFoldersAtom,
  toggleFolderExpansionAtom,
  expandFolderPathAtom,
  selectAndExpandFolderAtom,
  openCreateFolderModalAtom,
  openEditFolderModalAtom,
  openDeleteFolderModalAtom,
  closeAllFolderModalsAtom,
  showRemoveDocumentsModalAtom,
  removeDocumentsIdsAtom,
  openRemoveDocumentsModalAtom,
  closeRemoveDocumentsModalAtom,
} from "../folderAtoms";
import { CorpusFolderType } from "../../graphql/queries/folders";

/**
 * Build a minimal CorpusFolderType fixture. All callers can override fields.
 */
const makeFolder = (
  overrides: Partial<CorpusFolderType> & Pick<CorpusFolderType, "id" | "name">
): CorpusFolderType => ({
  description: "",
  color: "#000000",
  icon: "folder",
  tags: "[]",
  path: overrides.name,
  documentCount: 0,
  descendantDocumentCount: 0,
  created: "2024-01-01T00:00:00Z",
  modified: "2024-01-01T00:00:00Z",
  isPublic: false,
  parent: null,
  myPermissions: [],
  isPublished: false,
  ...overrides,
});

describe("folderAtoms — primitive atoms", () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  it("selectedFolderIdAtom defaults to null and accepts a string", () => {
    expect(store.get(selectedFolderIdAtom)).toBeNull();
    store.set(selectedFolderIdAtom, "folder-1");
    expect(store.get(selectedFolderIdAtom)).toBe("folder-1");
    store.set(selectedFolderIdAtom, null);
    expect(store.get(selectedFolderIdAtom)).toBeNull();
  });

  it("folderCorpusIdAtom defaults to null and is writable", () => {
    expect(store.get(folderCorpusIdAtom)).toBeNull();
    store.set(folderCorpusIdAtom, "corpus-42");
    expect(store.get(folderCorpusIdAtom)).toBe("corpus-42");
  });

  it("folderListAtom defaults to [] and accepts folder arrays", () => {
    expect(store.get(folderListAtom)).toEqual([]);
    const folders = [makeFolder({ id: "a", name: "A" })];
    store.set(folderListAtom, folders);
    expect(store.get(folderListAtom)).toEqual(folders);
  });

  it("corpusPermissionsAtom defaults to [] and is writable", () => {
    expect(store.get(corpusPermissionsAtom)).toEqual([]);
    store.set(corpusPermissionsAtom, ["read_corpus", "update_corpus"]);
    expect(store.get(corpusPermissionsAtom)).toEqual([
      "read_corpus",
      "update_corpus",
    ]);
  });

  it("modal visibility atoms default to false and round-trip", () => {
    const modalAtoms = [
      showCreateFolderModalAtom,
      showEditFolderModalAtom,
      showMoveFolderModalAtom,
      showDeleteFolderModalAtom,
      showRemoveDocumentsModalAtom,
    ];
    for (const atom of modalAtoms) {
      expect(store.get(atom)).toBe(false);
      store.set(atom, true);
      expect(store.get(atom)).toBe(true);
      store.set(atom, false);
      expect(store.get(atom)).toBe(false);
    }
  });

  it("activeFolderModalIdAtom, createFolderParentIdAtom default to null", () => {
    expect(store.get(activeFolderModalIdAtom)).toBeNull();
    expect(store.get(createFolderParentIdAtom)).toBeNull();
    store.set(activeFolderModalIdAtom, "f-1");
    store.set(createFolderParentIdAtom, "parent-1");
    expect(store.get(activeFolderModalIdAtom)).toBe("f-1");
    expect(store.get(createFolderParentIdAtom)).toBe("parent-1");
  });

  it("folderSearchQueryAtom defaults to '' and is writable", () => {
    expect(store.get(folderSearchQueryAtom)).toBe("");
    store.set(folderSearchQueryAtom, "contracts");
    expect(store.get(folderSearchQueryAtom)).toBe("contracts");
  });

  it("drag-and-drop atoms default to null and round-trip", () => {
    expect(store.get(draggingFolderIdAtom)).toBeNull();
    expect(store.get(dropTargetFolderIdAtom)).toBeNull();
    store.set(draggingFolderIdAtom, "src");
    store.set(dropTargetFolderIdAtom, "dst");
    expect(store.get(draggingFolderIdAtom)).toBe("src");
    expect(store.get(dropTargetFolderIdAtom)).toBe("dst");
  });

  it("removeDocumentsIdsAtom defaults to [] and round-trips", () => {
    expect(store.get(removeDocumentsIdsAtom)).toEqual([]);
    store.set(removeDocumentsIdsAtom, ["d-1", "d-2"]);
    expect(store.get(removeDocumentsIdsAtom)).toEqual(["d-1", "d-2"]);
  });
});

describe("folderAtoms — derived atoms", () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  describe("folderTreeAtom", () => {
    it("returns an empty array when no folders are loaded", () => {
      expect(store.get(folderTreeAtom)).toEqual([]);
    });

    it("assembles a flat list into a nested tree", () => {
      const folders = [
        makeFolder({ id: "root", name: "Root" }),
        makeFolder({
          id: "child",
          name: "Child",
          parent: { id: "root", name: "Root" },
        }),
        makeFolder({
          id: "grandchild",
          name: "Grand",
          parent: { id: "child", name: "Child" },
        }),
      ];
      store.set(folderListAtom, folders);
      const tree = store.get(folderTreeAtom);
      expect(tree).toHaveLength(1);
      expect(tree[0].id).toBe("root");
      expect(tree[0].children).toHaveLength(1);
      expect(tree[0].children[0].id).toBe("child");
      expect(tree[0].children[0].children[0].id).toBe("grandchild");
    });

    it("treats folders whose parent is not in the list as roots", () => {
      const folders = [
        makeFolder({
          id: "orphan",
          name: "Orphan",
          parent: { id: "missing", name: "Missing" },
        }),
      ];
      store.set(folderListAtom, folders);
      const tree = store.get(folderTreeAtom);
      expect(tree).toHaveLength(1);
      expect(tree[0].id).toBe("orphan");
    });

    it("parses tags JSON string into string[]", () => {
      store.set(folderListAtom, [
        makeFolder({ id: "t", name: "Tagged", tags: '["a","b"]' }),
      ]);
      expect(store.get(folderTreeAtom)[0].tags).toEqual(["a", "b"]);
    });
  });

  describe("folderBreadcrumbAtom", () => {
    it("returns [] when no folder is selected", () => {
      store.set(folderListAtom, [makeFolder({ id: "a", name: "A" })]);
      expect(store.get(folderBreadcrumbAtom)).toEqual([]);
    });

    it("returns path from root to selected folder", () => {
      store.set(folderListAtom, [
        makeFolder({ id: "root", name: "Root" }),
        makeFolder({
          id: "mid",
          name: "Mid",
          parent: { id: "root", name: "Root" },
        }),
        makeFolder({
          id: "leaf",
          name: "Leaf",
          parent: { id: "mid", name: "Mid" },
        }),
      ]);
      store.set(selectedFolderIdAtom, "leaf");
      const crumb = store.get(folderBreadcrumbAtom);
      expect(crumb.map((f) => f.id)).toEqual(["root", "mid", "leaf"]);
    });

    it("returns [] when selected folder is not in the list", () => {
      store.set(folderListAtom, [makeFolder({ id: "a", name: "A" })]);
      store.set(selectedFolderIdAtom, "missing");
      expect(store.get(folderBreadcrumbAtom)).toEqual([]);
    });
  });

  describe("folderMapAtom", () => {
    it("returns an empty map when no folders", () => {
      const map = store.get(folderMapAtom);
      expect(map).toBeInstanceOf(Map);
      expect(map.size).toBe(0);
    });

    it("indexes folders by id", () => {
      const a = makeFolder({ id: "a", name: "A" });
      const b = makeFolder({ id: "b", name: "B" });
      store.set(folderListAtom, [a, b]);
      const map = store.get(folderMapAtom);
      expect(map.size).toBe(2);
      expect(map.get("a")).toBe(a);
      expect(map.get("b")).toBe(b);
    });

    it("updates when folderListAtom changes", () => {
      store.set(folderListAtom, [makeFolder({ id: "a", name: "A" })]);
      expect(store.get(folderMapAtom).size).toBe(1);
      store.set(folderListAtom, []);
      expect(store.get(folderMapAtom).size).toBe(0);
    });
  });

  describe("canCreateFoldersAtom", () => {
    it("returns false when corpusPermissions is empty (fail-safe)", () => {
      expect(store.get(canCreateFoldersAtom)).toBe(false);
    });

    it("returns false when update_corpus permission is missing", () => {
      store.set(corpusPermissionsAtom, ["read_corpus"]);
      expect(store.get(canCreateFoldersAtom)).toBe(false);
    });

    it("returns true when update_corpus permission is present", () => {
      store.set(corpusPermissionsAtom, ["read_corpus", "update_corpus"]);
      expect(store.get(canCreateFoldersAtom)).toBe(true);
    });
  });
});

describe("folderAtoms — write-only action atoms", () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    // atomWithStorage persists to localStorage — isolate each test run.
    localStorage.clear();
    store = createStore();
  });

  describe("toggleFolderExpansionAtom", () => {
    it("adds a folder id to expanded set on first toggle", () => {
      store.set(toggleFolderExpansionAtom, "f-1");
      expect(store.get(expandedFolderIdsAtom).has("f-1")).toBe(true);
    });

    it("removes a folder id on subsequent toggle", () => {
      store.set(toggleFolderExpansionAtom, "f-1");
      store.set(toggleFolderExpansionAtom, "f-1");
      expect(store.get(expandedFolderIdsAtom).has("f-1")).toBe(false);
    });

    it("handles multiple folders independently", () => {
      store.set(toggleFolderExpansionAtom, "a");
      store.set(toggleFolderExpansionAtom, "b");
      const expanded = store.get(expandedFolderIdsAtom);
      expect(expanded.has("a")).toBe(true);
      expect(expanded.has("b")).toBe(true);
      expect(expanded.size).toBe(2);
    });
  });

  describe("expandFolderPathAtom", () => {
    it("expands the folder and all of its ancestors", () => {
      store.set(folderListAtom, [
        makeFolder({ id: "root", name: "Root" }),
        makeFolder({
          id: "mid",
          name: "Mid",
          parent: { id: "root", name: "Root" },
        }),
        makeFolder({
          id: "leaf",
          name: "Leaf",
          parent: { id: "mid", name: "Mid" },
        }),
      ]);
      store.set(expandFolderPathAtom, "leaf");
      const expanded = store.get(expandedFolderIdsAtom);
      expect(expanded.has("root")).toBe(true);
      expect(expanded.has("mid")).toBe(true);
      expect(expanded.has("leaf")).toBe(true);
    });

    it("stops safely when ancestor is missing from the list", () => {
      store.set(folderListAtom, [
        makeFolder({
          id: "leaf",
          name: "Leaf",
          parent: { id: "missing", name: "Missing" },
        }),
      ]);
      store.set(expandFolderPathAtom, "leaf");
      // leaf is expanded, but walk terminates at missing ancestor.
      expect(store.get(expandedFolderIdsAtom).has("leaf")).toBe(true);
    });
  });

  describe("selectAndExpandFolderAtom", () => {
    it("sets selected folder and expands the ancestor path", () => {
      store.set(folderListAtom, [
        makeFolder({ id: "root", name: "Root" }),
        makeFolder({
          id: "leaf",
          name: "Leaf",
          parent: { id: "root", name: "Root" },
        }),
      ]);
      store.set(selectAndExpandFolderAtom, "leaf");
      expect(store.get(selectedFolderIdAtom)).toBe("leaf");
      expect(store.get(expandedFolderIdsAtom).has("root")).toBe(true);
      expect(store.get(expandedFolderIdsAtom).has("leaf")).toBe(true);
    });

    it("clears selection and does not expand when given null", () => {
      store.set(selectedFolderIdAtom, "leaf");
      store.set(selectAndExpandFolderAtom, null);
      expect(store.get(selectedFolderIdAtom)).toBeNull();
      expect(store.get(expandedFolderIdsAtom).size).toBe(0);
    });
  });

  describe("folder modal openers", () => {
    it("openCreateFolderModalAtom opens with specified parent", () => {
      store.set(openCreateFolderModalAtom, "parent-1");
      expect(store.get(showCreateFolderModalAtom)).toBe(true);
      expect(store.get(createFolderParentIdAtom)).toBe("parent-1");
    });

    it("openCreateFolderModalAtom opens at root when parent is null", () => {
      store.set(openCreateFolderModalAtom, null);
      expect(store.get(showCreateFolderModalAtom)).toBe(true);
      expect(store.get(createFolderParentIdAtom)).toBeNull();
    });

    it("openEditFolderModalAtom opens with the active folder id", () => {
      store.set(openEditFolderModalAtom, "f-1");
      expect(store.get(showEditFolderModalAtom)).toBe(true);
      expect(store.get(activeFolderModalIdAtom)).toBe("f-1");
    });

    it("openDeleteFolderModalAtom opens with the active folder id", () => {
      store.set(openDeleteFolderModalAtom, "f-2");
      expect(store.get(showDeleteFolderModalAtom)).toBe(true);
      expect(store.get(activeFolderModalIdAtom)).toBe("f-2");
    });
  });

  describe("closeAllFolderModalsAtom", () => {
    it("resets all modal flags and ids", () => {
      store.set(showCreateFolderModalAtom, true);
      store.set(showEditFolderModalAtom, true);
      store.set(showMoveFolderModalAtom, true);
      store.set(showDeleteFolderModalAtom, true);
      store.set(activeFolderModalIdAtom, "f-1");
      store.set(createFolderParentIdAtom, "parent-1");

      store.set(closeAllFolderModalsAtom);

      expect(store.get(showCreateFolderModalAtom)).toBe(false);
      expect(store.get(showEditFolderModalAtom)).toBe(false);
      expect(store.get(showMoveFolderModalAtom)).toBe(false);
      expect(store.get(showDeleteFolderModalAtom)).toBe(false);
      expect(store.get(activeFolderModalIdAtom)).toBeNull();
      expect(store.get(createFolderParentIdAtom)).toBeNull();
    });
  });

  describe("remove-documents modal helpers", () => {
    it("openRemoveDocumentsModalAtom opens modal with target ids", () => {
      store.set(openRemoveDocumentsModalAtom, ["d-1", "d-2"]);
      expect(store.get(showRemoveDocumentsModalAtom)).toBe(true);
      expect(store.get(removeDocumentsIdsAtom)).toEqual(["d-1", "d-2"]);
    });

    it("closeRemoveDocumentsModalAtom resets modal and clears ids", () => {
      store.set(openRemoveDocumentsModalAtom, ["d-1"]);
      store.set(closeRemoveDocumentsModalAtom);
      expect(store.get(showRemoveDocumentsModalAtom)).toBe(false);
      expect(store.get(removeDocumentsIdsAtom)).toEqual([]);
    });
  });
});

describe("folderAtoms — atomWithStorage persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("expandedFolderIdsAtom serialises Set<string> to a JSON array in localStorage", async () => {
    const { expandedFolderIdsAtom: freshAtom } = await import("../folderAtoms");
    const store = createStore();
    store.set(freshAtom, new Set(["a", "b"]));
    const raw = localStorage.getItem("opencontracts:expandedFolderIds");
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw as string).sort()).toEqual(["a", "b"]);
  });

  it("expandedFolderIdsAtom hydrates from localStorage JSON array into a Set", async () => {
    localStorage.setItem(
      "opencontracts:expandedFolderIds",
      JSON.stringify(["x", "y"])
    );
    const { expandedFolderIdsAtom: freshAtom } = await import("../folderAtoms");
    const store = createStore();
    // atomWithStorage lazy-hydrates on subscribe (getOnInit defaults to false),
    // so subscribing triggers the custom getItem read from storage.
    const unsub = store.sub(freshAtom, () => {});
    const value = store.get(freshAtom);
    expect(value).toBeInstanceOf(Set);
    expect(value.has("x")).toBe(true);
    expect(value.has("y")).toBe(true);
    unsub();
  });

  it("expandedFolderIdsAtom falls back to initialValue on malformed JSON", async () => {
    localStorage.setItem("opencontracts:expandedFolderIds", "{not-json");
    const { expandedFolderIdsAtom: freshAtom } = await import("../folderAtoms");
    const store = createStore();
    // Subscribe to trigger the lazy getItem (hits the try/catch fallback path).
    const unsub = store.sub(freshAtom, () => {});
    const value = store.get(freshAtom);
    expect(value).toBeInstanceOf(Set);
    expect(value.size).toBe(0);
    unsub();
  });

  it("sidebarCollapsedAtom defaults to collapsed on narrow viewports", async () => {
    vi.stubGlobal("innerWidth", 600);
    const { sidebarCollapsedAtom } = await import("../folderAtoms");
    const store = createStore();
    expect(store.get(sidebarCollapsedAtom)).toBe(true);
  });

  it("sidebarCollapsedAtom defaults to expanded on desktop viewports", async () => {
    vi.stubGlobal("innerWidth", 1440);
    const { sidebarCollapsedAtom } = await import("../folderAtoms");
    const store = createStore();
    expect(store.get(sidebarCollapsedAtom)).toBe(false);
  });
});
