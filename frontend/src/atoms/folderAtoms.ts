import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";
import {
  CorpusFolderType,
  FolderTreeNode,
  buildFolderTree,
  buildFolderBreadcrumb,
  ParsedCorpusFolderType,
} from "../graphql/queries/folders";

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
 * Currently selected folder object (or null if root)
 */
export const currentFolderAtom = atom<CorpusFolderType | null>((get) => {
  const folderId = get(selectedFolderIdAtom);
  const folders = get(folderListAtom);

  if (!folderId) return null;

  return folders.find((f) => f.id === folderId) || null;
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
 */
export const sidebarCollapsedAtom = atomWithStorage<boolean>(
  "opencontracts:folderSidebarCollapsed",
  false
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
 * Currently dragging document ID
 */
export const draggingDocumentIdAtom = atom<string | null>(null);

/**
 * Drop target folder ID
 */
export const dropTargetFolderIdAtom = atom<string | null>(null);

/**
 * Whether drag-and-drop is enabled
 */
export const enableDragDropAtom = atom<boolean>(true);

// ============================================================================
// PERMISSION DERIVED ATOMS
// ============================================================================

/**
 * Can user create folders in current corpus?
 * Checks permissions on current folder or corpus
 */
export const canCreateFoldersAtom = atom<boolean>((get) => {
  const currentFolder = get(currentFolderAtom);

  // If we have a folder, check its permissions (inherited from corpus)
  if (currentFolder) {
    const perms = currentFolder.myPermissions;
    // Handle case where permissions haven't loaded yet
    if (!perms || !Array.isArray(perms)) return true;
    return perms.includes("update_corpus") || perms.includes("create_corpus");
  }

  // TODO: Check corpus permissions from Apollo cache
  // For now, return true as placeholder
  return true;
});

/**
 * Can user update currently selected folder?
 */
export const canUpdateCurrentFolderAtom = atom<boolean>((get) => {
  const currentFolder = get(currentFolderAtom);

  if (!currentFolder) return false;

  const perms = currentFolder.myPermissions;
  // Handle case where permissions haven't loaded yet
  if (!perms || !Array.isArray(perms)) return false;
  return perms.includes("update_corpus");
});

/**
 * Can user delete currently selected folder?
 */
export const canDeleteCurrentFolderAtom = atom<boolean>((get) => {
  const currentFolder = get(currentFolderAtom);

  if (!currentFolder) return false;

  const perms = currentFolder.myPermissions;
  // Handle case where permissions haven't loaded yet
  if (!perms || !Array.isArray(perms)) return false;
  return perms.includes("delete_corpus");
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
 * Collapse all folders in tree
 */
export const collapseAllFoldersAtom = atom(null, (_get, set) => {
  set(expandedFolderIdsAtom, new Set<string>());
});

/**
 * Expand all folders in tree
 */
export const expandAllFoldersAtom = atom(null, (get, set) => {
  const folders = get(folderListAtom);
  const allIds = new Set(folders.map((f) => f.id));
  set(expandedFolderIdsAtom, allIds);
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
 * Open move folder modal
 */
export const openMoveFolderModalAtom = atom(
  null,
  (_get, set, folderId: string) => {
    set(activeFolderModalIdAtom, folderId);
    set(showMoveFolderModalAtom, true);
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
