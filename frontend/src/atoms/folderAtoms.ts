import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";
import {
  CorpusFolderType,
  FolderTreeNode,
  buildFolderTree,
  buildFolderBreadcrumb,
  ParsedCorpusFolderType,
} from "../graphql/queries/folders";
import { TABLET_BREAKPOINT } from "../assets/configurations/constants";

/**
 * Corpus Folder State Management with Jotai
 *
 * Implementation Guide: docs/features/corpus_folders_implementation.md
 * API Reference: docs/features/corpus_folders_api_reference.md
 *
 * Architecture:
 * - selectedFolderIdAtom: Currently selected folder (null = corpus root)
 * - folderListAtom: Flat list from server (client builds tree)
 * - Derived atoms compute tree structure and breadcrumbs
 * - Expanded state persisted to localStorage
 */

// ============================================================================
// FOLDER SELECTION STATE
// ============================================================================

/**
 * Currently selected folder ID
 * - null: viewing corpus root
 * - string: viewing specific folder
 */
export const selectedFolderIdAtom = atom<string | null>(null);

/**
 * Currently selected corpus for folder context
 * This should be synced with routing
 */
export const folderCorpusIdAtom = atom<string | null>(null);

// ============================================================================
// FOLDER DATA STATE
// ============================================================================

/**
 * Flat list of folders from server
 * This is populated from GET_CORPUS_FOLDERS query
 * Client builds tree structure from this flat list
 */
export const folderListAtom = atom<CorpusFolderType[]>([]);

/**
 * Corpus permissions for the current folder context.
 * Populated by FolderDocumentBrowser from openedCorpus reactive var.
 * Used to determine if user can create/modify folders.
 */
export const corpusPermissionsAtom = atom<string[]>([]);

// ============================================================================
// DERIVED ATOMS (Computed from Base State)
// ============================================================================

/**
 * Folder tree built from flat list
 * Returns root-level folders with nested children
 */
export const folderTreeAtom = atom<FolderTreeNode[]>((get) => {
  const folders = get(folderListAtom);
  return buildFolderTree(folders);
});

/**
 * Breadcrumb path to currently selected folder
 * Returns array from root to current folder
 */
export const folderBreadcrumbAtom = atom<ParsedCorpusFolderType[]>((get) => {
  const folderId = get(selectedFolderIdAtom);
  const folders = get(folderListAtom);

  if (!folderId) return [];

  return buildFolderBreadcrumb(folderId, folders);
});

/**
 * Folder map for quick lookups
 */
export const folderMapAtom = atom<Map<string, CorpusFolderType>>((get) => {
  const folders = get(folderListAtom);
  return new Map(folders.map((f) => [f.id, f]));
});

// ============================================================================
// UI STATE
// ============================================================================

/**
 * Expanded folder IDs in tree view
 * Persisted to localStorage for user convenience
 */
export const expandedFolderIdsAtom = atomWithStorage<Set<string>>(
  "opencontracts:expandedFolderIds",
  new Set<string>(),
  {
    getItem: (key, initialValue) => {
      const stored = localStorage.getItem(key);
      if (!stored) return initialValue;
      try {
        const arr = JSON.parse(stored) as string[];
        return new Set(arr);
      } catch {
        return initialValue;
      }
    },
    setItem: (key, value) => {
      localStorage.setItem(key, JSON.stringify(Array.from(value)));
    },
    removeItem: (key) => {
      localStorage.removeItem(key);
    },
  }
);

/**
 * Sidebar collapsed state (persisted to localStorage)
 * Default: collapsed on mobile/tablet (<= TABLET_BREAKPOINT), expanded on desktop
 *
 * Uses TABLET_BREAKPOINT (768px) rather than MOBILE_VIEW_BREAKPOINT (600px) because
 * the folder sidebar takes significant screen real estate. On tablets (600-768px),
 * users benefit from having the sidebar collapsed by default while still having
 * easy access via the toggle button. This improves the document browsing experience
 * on medium-sized screens.
 */
const getDefaultSidebarCollapsed = (): boolean => {
  // SSR safety check
  if (typeof window === "undefined") return false;
  // Default to collapsed on mobile/tablet for better UX
  return window.innerWidth <= TABLET_BREAKPOINT;
};

export const sidebarCollapsedAtom = atomWithStorage<boolean>(
  "opencontracts:folderSidebarCollapsed",
  getDefaultSidebarCollapsed()
);

/**
 * Show/hide folder creation modal
 */
export const showCreateFolderModalAtom = atom<boolean>(false);

/**
 * Show/hide folder edit modal
 */
export const showEditFolderModalAtom = atom<boolean>(false);

/**
 * Show/hide folder move modal
 */
export const showMoveFolderModalAtom = atom<boolean>(false);

/**
 * Show/hide folder delete modal
 */
export const showDeleteFolderModalAtom = atom<boolean>(false);

/**
 * Folder currently being edited/moved/deleted
 */
export const activeFolderModalIdAtom = atom<string | null>(null);

/**
 * Parent folder for create operation
 * null = create at root level
 */
export const createFolderParentIdAtom = atom<string | null>(null);

/**
 * Tree search/filter query
 */
export const folderSearchQueryAtom = atom<string>("");

// ============================================================================
// DRAG AND DROP STATE
// ============================================================================

/**
 * Currently dragging folder ID
 */
export const draggingFolderIdAtom = atom<string | null>(null);

/**
 * Drop target folder ID
 */
export const dropTargetFolderIdAtom = atom<string | null>(null);

// ============================================================================
// PERMISSION DERIVED ATOMS
// ============================================================================

/**
 * Can user create folders in current corpus?
 * Checks UPDATE permission on the corpus (per permission model).
 * Folder write operations require corpus UPDATE permission.
 */
export const canCreateFoldersAtom = atom<boolean>((get) => {
  const corpusPermissions = get(corpusPermissionsAtom);

  // No permissions loaded yet - fail safe (hide button)
  if (!corpusPermissions || corpusPermissions.length === 0) {
    return false;
  }

  // Per permission model: folder write operations require UPDATE on corpus
  return corpusPermissions.includes("update_corpus");
});

// ============================================================================
// HELPER ACTIONS (Write-only Atoms)
// ============================================================================

/**
 * Toggle folder expansion in tree
 */
export const toggleFolderExpansionAtom = atom(
  null,
  (get, set, folderId: string) => {
    const expanded = new Set(get(expandedFolderIdsAtom));
    if (expanded.has(folderId)) {
      expanded.delete(folderId);
    } else {
      expanded.add(folderId);
    }
    set(expandedFolderIdsAtom, expanded);
  }
);

/**
 * Expand folder and all ancestors (for deep linking)
 */
export const expandFolderPathAtom = atom(null, (get, set, folderId: string) => {
  const folders = get(folderListAtom);
  const expanded = new Set(get(expandedFolderIdsAtom));

  // Walk up the tree and expand all ancestors
  let currentId: string | undefined = folderId;
  while (currentId) {
    expanded.add(currentId);
    const folder = folders.find((f) => f.id === currentId);
    currentId = folder?.parent?.id;
  }

  set(expandedFolderIdsAtom, expanded);
});

/**
 * Select folder and expand path to it
 */
export const selectAndExpandFolderAtom = atom(
  null,
  (get, set, folderId: string | null) => {
    set(selectedFolderIdAtom, folderId);
    if (folderId) {
      set(expandFolderPathAtom, folderId);
    }
  }
);

// ============================================================================
// MODAL HELPERS (Write-only Atoms)
// ============================================================================

/**
 * Open create folder modal with optional parent
 */
export const openCreateFolderModalAtom = atom(
  null,
  (_get, set, parentId: string | null = null) => {
    set(createFolderParentIdAtom, parentId);
    set(showCreateFolderModalAtom, true);
  }
);

/**
 * Open edit folder modal
 */
export const openEditFolderModalAtom = atom(
  null,
  (_get, set, folderId: string) => {
    set(activeFolderModalIdAtom, folderId);
    set(showEditFolderModalAtom, true);
  }
);

/**
 * Open delete folder modal
 */
export const openDeleteFolderModalAtom = atom(
  null,
  (_get, set, folderId: string) => {
    set(activeFolderModalIdAtom, folderId);
    set(showDeleteFolderModalAtom, true);
  }
);

/**
 * Close all folder modals
 */
export const closeAllFolderModalsAtom = atom(null, (_get, set) => {
  set(showCreateFolderModalAtom, false);
  set(showEditFolderModalAtom, false);
  set(showMoveFolderModalAtom, false);
  set(showDeleteFolderModalAtom, false);
  set(activeFolderModalIdAtom, null);
  set(createFolderParentIdAtom, null);
});

// ============================================================================
// REMOVE DOCUMENTS MODAL STATE
// ============================================================================

/**
 * Show/hide remove documents confirmation modal
 */
export const showRemoveDocumentsModalAtom = atom<boolean>(false);

/**
 * Document IDs to be removed (set when opening the modal)
 */
export const removeDocumentsIdsAtom = atom<string[]>([]);

/**
 * Open remove documents confirmation modal
 */
export const openRemoveDocumentsModalAtom = atom(
  null,
  (_get, set, documentIds: string[]) => {
    set(removeDocumentsIdsAtom, documentIds);
    set(showRemoveDocumentsModalAtom, true);
  }
);

/**
 * Close remove documents modal
 */
export const closeRemoveDocumentsModalAtom = atom(null, (_get, set) => {
  set(showRemoveDocumentsModalAtom, false);
  set(removeDocumentsIdsAtom, []);
});
