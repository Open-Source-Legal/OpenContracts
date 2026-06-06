import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  // Routing
  routeLoading,
  routeError,
  // Modals (UI reactive vars)
  showCookieAcceptModal,
  showAddDocsToCorpusModal,
  showRemoveDocsFromCorpusModal,
  showUploadNewDocumentsModal,
  showBulkImportModal,
  showDeleteDocumentsModal,
  showNewLabelsetModal,
  showExportModal,
  showUserSettingsModal,
  showGlobalSettingsModal,
  showSelectedAnnotationOnly,
  showAnnotationBoundingBoxes,
  showAnnotationLabels,
  pagesVisible,
  showDeleteExtractModal,
  showCreateExtractModal,
  showQueryViewState,
  showSelectCorpusAnalyzerOrFieldsetModal,
  viewStateVar,
  // Document state
  documentSearchTerm,
  openedDocument,
  selectedDocVersion,
  selectedDocumentIds,
  viewingDocument,
  editingDocument,
  currentViewTotalDocumentCount,
  documentsLoading,
  linkDocumentsModalState,
  // Extract
  openedExtract,
  selectedExtractIds,
  selectedExtract,
  extractSearchTerm,
  // Corpus
  corpusSearchTerm,
  filterToCorpus,
  selectedCorpus,
  openedCorpus,
  viewingCorpus,
  deletingCorpus,
  editingCorpus,
  exportingCorpus,
  selectedCorpusIds,
  showAnalyzerSelectionForCorpus,
  showCorpusActionOutputs,
  // LabelSet
  labelsetSearchTerm,
  filterToLabelsetId,
  openedLabelset,
  deletingLabelset,
  editingLabelset,
  selectedLabelsetIds,
  // Annotations
  filterToAnnotationType,
  filterToLabelId,
  selectedAnnotation,
  showStructuralAnnotations,
  filterToStructuralAnnotations,
  displayAnnotationOnAnnotatorLoad,
  onlyDisplayTheseAnnotations,
  annotationContentSearchTerm,
  selectedMetaAnnotationId,
  includeStructuralAnnotations,
  selectedAnnotationIds,
  // Analysis
  selectedAnalysesIds,
  selectedAnalysis,
  selectedAnalyses,
  analysisSearchTerm,
  // Export
  exportSearchTerm,
  selectedFieldset,
  // Thread
  openedThread,
  selectedThreadId,
  // Folder/tab URL state
  selectedFolderId,
  selectedTab,
  selectedMessageId,
  corpusHomeView,
  tocExpandAll,
  corpusDetailView,
  corpusPowerUserMode,
  highlightedTextBlock,
  // Auth
  userObj,
  authToken,
  uploadModalPreloadedFiles,
  showBulkUploadModal,
  backendUserObj,
  authStatusVar,
  authInitCompleteVar,
  // Cache & field policies
  cache,
  mergeArrayByIdFieldPolicy,
  ContextAwareRelayStylePaginationKeyArgsFunction,
  // Persisted
  showKnowledgeBaseModal,
} from "../cache";
import { LabelDisplayBehavior } from "../../types/graphql-api";
import { ViewState } from "../../components/types";

describe("cache.ts — reactive var initial values", () => {
  it("routing vars default to not-loading and no error", () => {
    expect(routeLoading()).toBe(false);
    expect(routeError()).toBeNull();
  });

  it("all boolean UI modal vars default to false (except showCorpusActionOutputs)", () => {
    const falseModals = [
      showCookieAcceptModal,
      showAddDocsToCorpusModal,
      showRemoveDocsFromCorpusModal,
      showUploadNewDocumentsModal,
      showBulkImportModal,
      showDeleteDocumentsModal,
      showNewLabelsetModal,
      showExportModal,
      showUserSettingsModal,
      showGlobalSettingsModal,
      showAnnotationBoundingBoxes,
      showDeleteExtractModal,
      showCreateExtractModal,
      showSelectCorpusAnalyzerOrFieldsetModal,
      showBulkUploadModal,
      documentsLoading,
      includeStructuralAnnotations,
      showStructuralAnnotations,
      tocExpandAll,
      corpusPowerUserMode,
      authInitCompleteVar,
    ];
    for (const v of falseModals) {
      expect(v()).toBe(false);
    }
  });

  it("showSelectedAnnotationOnly defaults to true", () => {
    expect(showSelectedAnnotationOnly()).toBe(true);
  });

  it("currentViewTotalDocumentCount defaults to 0", () => {
    expect(currentViewTotalDocumentCount()).toBe(0);
  });

  it("showCorpusActionOutputs defaults to true", () => {
    expect(showCorpusActionOutputs()).toBe(true);
  });

  it("showAnnotationLabels defaults to ON_HOVER", () => {
    expect(showAnnotationLabels()).toBe(LabelDisplayBehavior.ON_HOVER);
  });

  it("viewStateVar defaults to LOADING", () => {
    expect(viewStateVar()).toBe(ViewState.LOADING);
  });

  it("showQueryViewState defaults to ASK", () => {
    expect(showQueryViewState()).toBe("ASK");
  });

  it("filterToStructuralAnnotations defaults to EXCLUDE", () => {
    expect(filterToStructuralAnnotations()).toBe("EXCLUDE");
  });

  it("authStatusVar defaults to LOADING", () => {
    expect(authStatusVar()).toBe("LOADING");
  });

  it("corpusDetailView defaults to 'landing'", () => {
    expect(corpusDetailView()).toBe("landing");
  });

  it("all 'null' entity vars are initialised to null", () => {
    const nullVars = [
      openedDocument,
      selectedDocVersion,
      viewingDocument,
      editingDocument,
      openedExtract,
      selectedExtract,
      filterToCorpus,
      selectedCorpus,
      openedCorpus,
      viewingCorpus,
      deletingCorpus,
      editingCorpus,
      exportingCorpus,
      showAnalyzerSelectionForCorpus,
      filterToLabelsetId,
      openedLabelset,
      deletingLabelset,
      editingLabelset,
      filterToAnnotationType,
      selectedAnnotation,
      selectedAnalysis,
      selectedFieldset,
      openedThread,
      selectedThreadId,
      selectedFolderId,
      selectedTab,
      selectedMessageId,
      corpusHomeView,
      highlightedTextBlock,
      userObj,
      backendUserObj,
    ];
    for (const v of nullVars) {
      expect(v()).toBeNull();
    }
  });

  it("undefined-typed annotation display vars default to undefined", () => {
    expect(displayAnnotationOnAnnotatorLoad()).toBeUndefined();
    expect(onlyDisplayTheseAnnotations()).toBeUndefined();
  });

  it("empty-string search terms default to ''", () => {
    const searchTerms = [
      documentSearchTerm,
      extractSearchTerm,
      corpusSearchTerm,
      labelsetSearchTerm,
      filterToLabelId,
      annotationContentSearchTerm,
      selectedMetaAnnotationId,
      analysisSearchTerm,
      exportSearchTerm,
      authToken,
    ];
    for (const v of searchTerms) {
      expect(v()).toBe("");
    }
  });

  it("collection-typed vars default to [] or {}", () => {
    expect(selectedDocumentIds()).toEqual([]);
    expect(selectedExtractIds()).toEqual([]);
    expect(selectedCorpusIds()).toEqual([]);
    expect(selectedLabelsetIds()).toEqual([]);
    expect(selectedAnnotationIds()).toEqual([]);
    expect(selectedAnalysesIds()).toEqual([]);
    expect(selectedAnalyses()).toEqual([]);
    expect(uploadModalPreloadedFiles()).toEqual([]);
    expect(pagesVisible()).toEqual({});
  });

  it("linkDocumentsModalState defaults to closed with empty id lists", () => {
    expect(linkDocumentsModalState()).toEqual({
      open: false,
      initialSourceIds: [],
      initialTargetIds: [],
    });
  });
});

describe("cache.ts — reactive var round-trip", () => {
  it("mutating a boolean var updates the getter", () => {
    expect(showCookieAcceptModal()).toBe(false);
    showCookieAcceptModal(true);
    expect(showCookieAcceptModal()).toBe(true);
    // Restore state for test isolation across files.
    showCookieAcceptModal(false);
  });

  it("mutating viewStateVar through each state works", () => {
    try {
      viewStateVar(ViewState.LOADED);
      expect(viewStateVar()).toBe(ViewState.LOADED);
      viewStateVar(ViewState.NOT_FOUND);
      expect(viewStateVar()).toBe(ViewState.NOT_FOUND);
      viewStateVar(ViewState.ERROR);
      expect(viewStateVar()).toBe(ViewState.ERROR);
    } finally {
      viewStateVar(ViewState.LOADING);
    }
  });

  it("selectedDocumentIds round-trips an array", () => {
    try {
      selectedDocumentIds(["a", "b"]);
      expect(selectedDocumentIds()).toEqual(["a", "b"]);
    } finally {
      selectedDocumentIds([]);
    }
  });

  it("linkDocumentsModalState round-trips struct update", () => {
    try {
      linkDocumentsModalState({
        open: true,
        initialSourceIds: ["s"],
        initialTargetIds: ["t"],
      });
      const state = linkDocumentsModalState();
      expect(state.open).toBe(true);
      expect(state.initialSourceIds).toEqual(["s"]);
      expect(state.initialTargetIds).toEqual(["t"]);
    } finally {
      linkDocumentsModalState({
        open: false,
        initialSourceIds: [],
        initialTargetIds: [],
      });
    }
  });

  it("authStatusVar cycles through lifecycle states", () => {
    try {
      authStatusVar("AUTHENTICATED");
      expect(authStatusVar()).toBe("AUTHENTICATED");
      authStatusVar("ANONYMOUS");
      expect(authStatusVar()).toBe("ANONYMOUS");
    } finally {
      authStatusVar("LOADING");
    }
  });

  it("routeError accepts and returns an Error instance", () => {
    try {
      const err = new Error("boom");
      routeError(err);
      expect(routeError()).toBe(err);
    } finally {
      routeError(null);
    }
  });
});

describe("cache.ts — mergeArrayByIdFieldPolicy", () => {
  // Minimal readField/mergeObjects shims matching Apollo field policy context.
  // The policy treats incoming references as opaque and uses readField to look
  // up the "id" field; we pass plain objects for test simplicity.
  const readField = <T>(fieldName: string, obj: unknown): T | undefined => {
    return (obj as Record<string, T>)?.[fieldName];
  };
  const mergeObjects = <T extends object>(a: T, b: T): T => ({ ...a, ...b });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mergeFn = mergeArrayByIdFieldPolicy.merge as any;

  it("replaces existing items with incoming items sharing an id", () => {
    const existing = [
      { id: "1", name: "old-1" },
      { id: "2", name: "old-2" },
    ];
    const incoming = [
      { id: "1", name: "new-1" },
      { id: "3", name: "new-3" },
    ];
    const merged = mergeFn(existing, incoming, {
      readField,
      mergeObjects,
    });
    // Output is the incoming list with id-1 merged with existing id-1 entry.
    expect(merged).toHaveLength(2);
    expect(merged).toContainEqual({ id: "1", name: "new-1" });
    expect(merged).toContainEqual({ id: "3", name: "new-3" });
  });

  it("defaults existing and incoming to [] when not provided", () => {
    const merged = mergeFn(undefined, undefined, {
      readField,
      mergeObjects,
    });
    expect(merged).toEqual([]);
  });
});

describe("cache.ts — ContextAwareRelayStylePaginationKeyArgsFunction", () => {
  // The `annotations` root field is a single GraphQL field shared by the
  // corpus annotation list, the card grid, AND the document index. Its Relay
  // cache list must be keyed by its *filter* arguments, or those queries
  // collide on one entry and `cache-first` serves the wrong document's
  // sections until the network response replaces them (the document-index
  // "stale OC_SECTION refs" bug).
  const ctx = (fieldName: string) => ({
    typename: "Query",
    fieldName,
    field: null,
    variables: {},
  });

  it("derives distinct keys for the same field with different documentIds", () => {
    const keyA = ContextAwareRelayStylePaginationKeyArgsFunction(
      {
        documentId: "DocA",
        corpusId: "Corpus1",
        annotationLabel_Text: "OC_SECTION",
        structural: false,
        first: 500,
      },
      ctx("annotations")
    );
    const keyB = ContextAwareRelayStylePaginationKeyArgsFunction(
      {
        documentId: "DocB",
        corpusId: "Corpus1",
        annotationLabel_Text: "OC_SECTION",
        structural: false,
        first: 500,
      },
      ctx("annotations")
    );
    expect(keyA).not.toEqual(keyB);
    expect(String(keyA)).toContain("DocA");
    expect(String(keyB)).toContain("DocB");
  });

  it("ignores Relay pagination cursors so pages of one filter set share a key", () => {
    const page1 = ContextAwareRelayStylePaginationKeyArgsFunction(
      { documentId: "DocA", structural: false, first: 100 },
      ctx("annotations")
    );
    const page2 = ContextAwareRelayStylePaginationKeyArgsFunction(
      { documentId: "DocA", structural: false, first: 100, after: "cursor-99" },
      ctx("annotations")
    );
    expect(page1).toEqual(page2);
  });

  it("keeps separately-aliased copies of the field in distinct lists", () => {
    const sameArgs = { documentId: "DocA", structural: false };
    const aliasA = ContextAwareRelayStylePaginationKeyArgsFunction(sameArgs, {
      typename: "Query",
      fieldName: "annotations",
      field: { alias: { value: "indexAnnotations" } } as never,
      variables: {},
    });
    const aliasB = ContextAwareRelayStylePaginationKeyArgsFunction(sameArgs, {
      typename: "Query",
      fieldName: "annotations",
      field: { alias: { value: "feedAnnotations" } } as never,
      variables: {},
    });
    expect(aliasA).not.toEqual(aliasB);
  });

  it("falls back to the bare field name when there are no args", () => {
    expect(
      ContextAwareRelayStylePaginationKeyArgsFunction(null, ctx("annotations"))
    ).toEqual("annotations");
  });
});

describe("cache.ts — InMemoryCache configuration", () => {
  it("exposes the shared InMemoryCache instance", () => {
    expect(cache).toBeDefined();
    // Proves it implements the InMemoryCache surface we rely on.
    expect(typeof cache.extract).toBe("function");
    expect(typeof cache.reset).toBe("function");
  });

  it("cache.extract returns a serialisable snapshot object", () => {
    expect(typeof cache.extract()).toBe("object");
  });
});

describe("cache.ts — showKnowledgeBaseModal (persistentVar)", () => {
  const STORAGE_KEY = "oc_kbModal";

  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
    // Restore the module-level var to its default for other test blocks.
    showKnowledgeBaseModal({
      isOpen: false,
      documentId: null,
      corpusId: null,
      annotationIds: null,
    });
  });

  it("defaults to closed with null document/corpus when storage is empty", () => {
    const val = showKnowledgeBaseModal();
    expect(val.isOpen).toBe(false);
    expect(val.documentId).toBeNull();
    expect(val.corpusId).toBeNull();
  });

  it("writes the first post-init change to sessionStorage", async () => {
    // Use an isolated module to guarantee the onNextChange listener is fresh
    // (Apollo's onNextChange is one-shot, so subsequent writes on an already-
    // notified var would no-op on the persistence side).
    sessionStorage.clear();
    vi.resetModules();
    const mod = await import("../cache");
    mod.showKnowledgeBaseModal({
      isOpen: true,
      documentId: "d-1",
      corpusId: "c-1",
      annotationIds: ["a-1"],
    });
    const stored = sessionStorage.getItem(STORAGE_KEY);
    expect(stored).not.toBeNull();
    expect(JSON.parse(stored as string)).toEqual({
      isOpen: true,
      documentId: "d-1",
      corpusId: "c-1",
      annotationIds: ["a-1"],
    });
  });

  it("re-hydrates from sessionStorage on module re-import", async () => {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        isOpen: true,
        documentId: "d-hydrate",
        corpusId: "c-hydrate",
        annotationIds: null,
      })
    );
    vi.resetModules();
    const mod = await import("../cache");
    const val = mod.showKnowledgeBaseModal();
    expect(val.isOpen).toBe(true);
    expect(val.documentId).toBe("d-hydrate");
    expect(val.corpusId).toBe("c-hydrate");
  });

  it("ignores non-JSON sessionStorage entries and falls back to default", async () => {
    sessionStorage.setItem(STORAGE_KEY, "{not-json");
    vi.resetModules();
    const mod = await import("../cache");
    const val = mod.showKnowledgeBaseModal();
    expect(val.isOpen).toBe(false);
    expect(val.documentId).toBeNull();
    expect(val.corpusId).toBeNull();
  });
});
