import React from "react";
import { useHydrateAtoms } from "jotai/utils";
import { FolderBreadcrumb } from "../../../src/components/corpuses/folders/FolderBreadcrumb";
import { CreateFolderModal } from "../../../src/components/corpuses/folders/CreateFolderModal";
import {
  FolderToolbar,
  ViewMode,
} from "../../../src/components/corpuses/folders/FolderToolbar";
import { RemoveDocumentsModal } from "../../../src/components/corpuses/folders/RemoveDocumentsModal";
import { DeleteFolderModal } from "../../../src/components/corpuses/folders/DeleteFolderModal";
import { EditFolderModal } from "../../../src/components/corpuses/folders/EditFolderModal";
import { MoveFolderModal } from "../../../src/components/corpuses/folders/MoveFolderModal";
import {
  selectedFolderIdAtom,
  folderListAtom,
  showCreateFolderModalAtom,
  createFolderParentIdAtom,
  folderCorpusIdAtom,
  sidebarCollapsedAtom,
  corpusPermissionsAtom,
  showRemoveDocumentsModalAtom,
  removeDocumentsIdsAtom,
  showDeleteFolderModalAtom,
  showEditFolderModalAtom,
  showMoveFolderModalAtom,
  activeFolderModalIdAtom,
} from "../../../src/atoms/folderAtoms";
import { CorpusFolderType } from "../../../src/graphql/queries/folders";

/**
 * Test fixtures for folder components
 * These are separate components that can be imported and mounted in tests
 */

interface BreadcrumbFixtureProps {
  folderId: string | null;
  folders: any[];
  maxDepth?: number;
}

export function BreadcrumbFixture({
  folderId,
  folders,
  maxDepth,
}: BreadcrumbFixtureProps) {
  useHydrateAtoms([
    [selectedFolderIdAtom, folderId],
    [folderListAtom, folders],
  ]);
  return <FolderBreadcrumb maxDepth={maxDepth} />;
}

interface ModalFixtureProps {
  showModal?: boolean;
  parentId?: string | null;
  folders?: any[];
}

export function CreateModalFixture({
  showModal = true,
  parentId = null,
  folders = [],
}: ModalFixtureProps) {
  useHydrateAtoms([
    [showCreateFolderModalAtom, showModal],
    [createFolderParentIdAtom, parentId],
    [folderCorpusIdAtom, "corpus-1"],
    [folderListAtom, folders],
  ]);
  return <CreateFolderModal />;
}

// Re-export ViewMode for tests
export type { ViewMode };

interface ToolbarFixtureProps {
  showSidebar?: boolean;
  selectedFolderId?: string | null;
  canGoBack?: boolean;
  viewMode?: ViewMode;
  canCreateFolders?: boolean;
  onViewModeChange?: (mode: ViewMode) => void;
  onFolderSelect?: (folderId: string | null) => void;
  onGoBack?: () => void;
  onGoUp?: () => void;
  onNewFolder?: () => void;
  onUpload?: () => void;
  // Selection-related props
  selectedDocumentCount?: number;
  totalDocumentCount?: number;
  onSelectAll?: () => void;
  onClearSelection?: () => void;
  onRemoveFromCorpus?: () => void;
  onEmptyCorpus?: () => void;
  allSelected?: boolean;
  isLoading?: boolean;
}

export function ToolbarFixture({
  showSidebar = true,
  selectedFolderId = null,
  canGoBack = false,
  viewMode = "modern-list",
  canCreateFolders = true,
  onViewModeChange = () => {},
  onFolderSelect = () => {},
  onGoBack = () => {},
  onGoUp = () => {},
  onNewFolder = () => {},
  onUpload = () => {},
  // Selection props with defaults
  selectedDocumentCount = 0,
  totalDocumentCount = 0,
  onSelectAll,
  onClearSelection,
  onRemoveFromCorpus,
  onEmptyCorpus,
  allSelected = false,
  isLoading = false,
}: ToolbarFixtureProps) {
  // canCreateFoldersAtom now reads from corpusPermissionsAtom
  // which checks for "update_corpus" permission on the corpus
  const corpusPermissions = canCreateFolders
    ? ["read_corpus", "update_corpus"]
    : ["read_corpus"];

  // Hydrate atoms for the toolbar to read from
  // canCreateFoldersAtom is derived from corpusPermissionsAtom
  useHydrateAtoms([
    [selectedFolderIdAtom, selectedFolderId],
    [folderListAtom, []],
    [sidebarCollapsedAtom, false],
    [corpusPermissionsAtom, corpusPermissions],
  ] as const);

  return (
    <div style={{ width: "100%", minHeight: "60px" }}>
      <FolderToolbar
        showSidebar={showSidebar}
        selectedFolderId={selectedFolderId}
        canGoBack={canGoBack}
        viewMode={viewMode}
        onViewModeChange={onViewModeChange}
        onFolderSelect={onFolderSelect}
        onGoBack={onGoBack}
        onGoUp={onGoUp}
        onNewFolder={onNewFolder}
        onUpload={onUpload}
        selectedDocumentCount={selectedDocumentCount}
        totalDocumentCount={totalDocumentCount}
        onSelectAll={onSelectAll}
        onClearSelection={onClearSelection}
        onRemoveFromCorpus={onRemoveFromCorpus}
        onEmptyCorpus={onEmptyCorpus}
        allSelected={allSelected}
        isLoading={isLoading}
      />
    </div>
  );
}

// ============================================================================
// Remove Documents Modal Fixture
// ============================================================================

interface RemoveDocumentsModalFixtureProps {
  showModal?: boolean;
  documentIds?: string[];
  corpusId?: string;
}

export function RemoveDocumentsModalFixture({
  showModal = true,
  documentIds = [],
  corpusId = "corpus-1",
}: RemoveDocumentsModalFixtureProps) {
  useHydrateAtoms([
    [showRemoveDocumentsModalAtom, showModal],
    [removeDocumentsIdsAtom, documentIds],
    [folderCorpusIdAtom, corpusId],
  ] as const);

  return <RemoveDocumentsModal />;
}

// ============================================================================
// Delete Folder Modal Fixture
// ============================================================================

interface DeleteFolderModalFixtureProps {
  showModal?: boolean;
  folderId?: string | null;
  folders?: CorpusFolderType[];
  corpusId?: string;
}

export function DeleteFolderModalFixture({
  showModal = true,
  folderId = "folder-1",
  folders = [],
  corpusId = "corpus-1",
}: DeleteFolderModalFixtureProps) {
  useHydrateAtoms([
    [showDeleteFolderModalAtom, showModal],
    [activeFolderModalIdAtom, folderId],
    [folderListAtom, folders],
    [folderCorpusIdAtom, corpusId],
  ] as const);

  return <DeleteFolderModal />;
}

// ============================================================================
// Edit Folder Modal Fixture
// ============================================================================

interface EditFolderModalFixtureProps {
  showModal?: boolean;
  folderId?: string | null;
  folders?: CorpusFolderType[];
  corpusId?: string;
}

export function EditFolderModalFixture({
  showModal = true,
  folderId = "folder-1",
  folders = [],
  corpusId = "corpus-1",
}: EditFolderModalFixtureProps) {
  useHydrateAtoms([
    [showEditFolderModalAtom, showModal],
    [activeFolderModalIdAtom, folderId],
    [folderListAtom, folders],
    [folderCorpusIdAtom, corpusId],
  ] as const);

  return <EditFolderModal />;
}

// ============================================================================
// Move Folder Modal Fixture
// ============================================================================

interface MoveFolderModalFixtureProps {
  showModal?: boolean;
  folderId?: string | null;
  folders?: CorpusFolderType[];
  corpusId?: string;
}

export function MoveFolderModalFixture({
  showModal = true,
  folderId = "folder-1",
  folders = [],
  corpusId = "corpus-1",
}: MoveFolderModalFixtureProps) {
  useHydrateAtoms([
    [showMoveFolderModalAtom, showModal],
    [activeFolderModalIdAtom, folderId],
    [folderListAtom, folders],
    [folderCorpusIdAtom, corpusId],
  ] as const);

  return <MoveFolderModal />;
}
