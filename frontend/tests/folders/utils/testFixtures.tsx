import React from "react";
import { useHydrateAtoms } from "jotai/utils";
import { FolderBreadcrumb } from "../../../src/components/corpuses/folders/FolderBreadcrumb";
import { CreateFolderModal } from "../../../src/components/corpuses/folders/CreateFolderModal";
import {
  selectedFolderIdAtom,
  folderListAtom,
  showCreateFolderModalAtom,
  createFolderParentIdAtom,
  folderCorpusIdAtom,
} from "../../../src/atoms/folderAtoms";

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
