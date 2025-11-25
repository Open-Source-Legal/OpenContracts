import { gql } from "@apollo/client";

/**
 * Corpus Folder Queries and Mutations
 *
 * API Reference: docs/features/corpus_folders_api_reference.md
 * Implementation Guide: docs/features/corpus_folders_implementation.md
 */

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// QUERIES
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface GetCorpusFoldersInputs {
  corpusId: string;
}

export interface GetCorpusFoldersOutputs {
  corpusFolders: CorpusFolderType[];
}

export const GET_CORPUS_FOLDERS = gql`
  query GetCorpusFolders($corpusId: ID!) {
    corpusFolders(corpusId: $corpusId) {
      id
      name
      description
      color
      icon
      tags
      path
      documentCount
      descendantDocumentCount
      created
      modified
      isPublic
      parent {
        id
        name
      }
      myPermissions
      isPublished
    }
  }
`;

export interface GetCorpusFolderInputs {
  id: string;
}

export interface GetCorpusFolderOutputs {
  corpusFolder: CorpusFolderType;
}

export const GET_CORPUS_FOLDER = gql`
  query GetCorpusFolder($id: ID!) {
    corpusFolder(id: $id) {
      id
      name
      description
      color
      icon
      tags
      path
      documentCount
      descendantDocumentCount
      created
      modified
      isPublic
      parent {
        id
        name
      }
      children {
        id
        name
        documentCount
        color
        icon
      }
      myPermissions
      isPublished
    }
  }
`;

export interface DeletedDocumentPathType {
  id: string;
  path: string;
  versionNumber: number;
  modified: string;
  createdBy: {
    id: string;
    username: string;
  };
  document: {
    id: string;
    title: string;
    description: string;
    icon: string;
    fileType: string;
    pageCount: number;
    pdfFile: string;
  };
  folder: {
    id: string;
    name: string;
  } | null;
}

export interface GetDeletedDocumentsInputs {
  corpusId: string;
}

export interface GetDeletedDocumentsOutputs {
  deletedDocumentsInCorpus: DeletedDocumentPathType[];
}

export const GET_DELETED_DOCUMENTS_IN_CORPUS = gql`
  query GetDeletedDocumentsInCorpus($corpusId: ID!) {
    deletedDocumentsInCorpus(corpusId: $corpusId) {
      id
      path
      versionNumber
      modified
      createdBy {
        id
        username
      }
      document {
        id
        title
        description
        icon
        fileType
        pageCount
        pdfFile
      }
      folder {
        id
        name
      }
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// MUTATIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

export interface CreateCorpusFolderInputs {
  corpusId: string;
  name: string;
  parentId?: string;
  description?: string;
  color?: string;
  icon?: string;
  tags?: string[];
}

export interface CreateCorpusFolderOutputs {
  createCorpusFolder: {
    ok: boolean;
    message: string;
    folder?: CorpusFolderType;
  };
}

export const CREATE_CORPUS_FOLDER = gql`
  mutation CreateCorpusFolder(
    $corpusId: ID!
    $name: String!
    $parentId: ID
    $description: String
    $color: String
    $icon: String
    $tags: [String]
  ) {
    createCorpusFolder(
      corpusId: $corpusId
      name: $name
      parentId: $parentId
      description: $description
      color: $color
      icon: $icon
      tags: $tags
    ) {
      ok
      message
      folder {
        id
        name
        description
        color
        icon
        tags
        path
        documentCount
        parent {
          id
          name
        }
      }
    }
  }
`;

export interface UpdateCorpusFolderInputs {
  folderId: string;
  name?: string;
  description?: string;
  color?: string;
  icon?: string;
  tags?: string[];
}

export interface UpdateCorpusFolderOutputs {
  updateCorpusFolder: {
    ok: boolean;
    message: string;
    folder?: CorpusFolderType;
  };
}

export const UPDATE_CORPUS_FOLDER = gql`
  mutation UpdateCorpusFolder(
    $folderId: ID!
    $name: String
    $description: String
    $color: String
    $icon: String
    $tags: [String]
  ) {
    updateCorpusFolder(
      folderId: $folderId
      name: $name
      description: $description
      color: $color
      icon: $icon
      tags: $tags
    ) {
      ok
      message
      folder {
        id
        name
        description
        color
        icon
        tags
        path
        modified
      }
    }
  }
`;

export interface MoveCorpusFolderInputs {
  folderId: string;
  newParentId?: string | null;
}

export interface MoveCorpusFolderOutputs {
  moveCorpusFolder: {
    ok: boolean;
    message: string;
    folder?: CorpusFolderType;
  };
}

export const MOVE_CORPUS_FOLDER = gql`
  mutation MoveCorpusFolder($folderId: ID!, $newParentId: ID) {
    moveCorpusFolder(folderId: $folderId, newParentId: $newParentId) {
      ok
      message
      folder {
        id
        name
        path
        parent {
          id
          name
        }
      }
    }
  }
`;

export interface DeleteCorpusFolderInputs {
  folderId: string;
  deleteContents?: boolean;
}

export interface DeleteCorpusFolderOutputs {
  deleteCorpusFolder: {
    ok: boolean;
    message: string;
  };
}

export const DELETE_CORPUS_FOLDER = gql`
  mutation DeleteCorpusFolder($folderId: ID!, $deleteContents: Boolean) {
    deleteCorpusFolder(folderId: $folderId, deleteContents: $deleteContents) {
      ok
      message
    }
  }
`;

export interface MoveDocumentToFolderInputs {
  documentId: string;
  corpusId: string;
  folderId?: string | null;
}

export interface MoveDocumentToFolderOutputs {
  moveDocumentToFolder: {
    ok: boolean;
    message: string;
    document?: {
      id: string;
      title: string;
    };
  };
}

export const MOVE_DOCUMENT_TO_FOLDER = gql`
  mutation MoveDocumentToFolder(
    $documentId: ID!
    $corpusId: ID!
    $folderId: ID
  ) {
    moveDocumentToFolder(
      documentId: $documentId
      corpusId: $corpusId
      folderId: $folderId
    ) {
      ok
      message
      document {
        id
        title
      }
    }
  }
`;

export interface MoveDocumentsToFolderInputs {
  documentIds: string[];
  corpusId: string;
  folderId?: string | null;
}

export interface MoveDocumentsToFolderOutputs {
  moveDocumentsToFolder: {
    ok: boolean;
    message: string;
    movedCount: number;
  };
}

export const MOVE_DOCUMENTS_TO_FOLDER = gql`
  mutation MoveDocumentsToFolder(
    $documentIds: [ID]!
    $corpusId: ID!
    $folderId: ID
  ) {
    moveDocumentsToFolder(
      documentIds: $documentIds
      corpusId: $corpusId
      folderId: $folderId
    ) {
      ok
      message
      movedCount
    }
  }
`;

///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/// TYPE DEFINITIONS
///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

/**
 * CorpusFolderType represents a folder within a corpus for organizing documents.
 * Folders form a tree hierarchy using parent/children relationships.
 */
export interface CorpusFolderType {
  id: string;
  name: string;
  description: string;
  color: string;
  icon: string;
  tags: string; // JSON string, parse with JSON.parse() to get string[]
  path: string; // Full path from root (e.g., "Legal/Contracts/2024")
  documentCount: number; // Documents directly in this folder
  descendantDocumentCount: number; // Documents in this folder + all subfolders
  created: string; // ISO datetime string
  modified: string; // ISO datetime string
  isPublic: boolean;
  parent: {
    id: string;
    name: string;
  } | null;
  children?: Array<{
    id: string;
    name: string;
    documentCount?: number;
    color?: string;
    icon?: string;
  }>;
  myPermissions: string[]; // Inherited from corpus
  isPublished: boolean;
}

/**
 * Parsed version of folder tags (for convenience)
 */
export interface ParsedCorpusFolderType extends Omit<CorpusFolderType, "tags"> {
  tags: string[];
}

/**
 * Helper to parse folder tags from JSON string to array
 */
export function parseCorpusFolderTags(
  folder: CorpusFolderType
): ParsedCorpusFolderType {
  return {
    ...folder,
    tags:
      typeof folder.tags === "string" ? JSON.parse(folder.tags) : folder.tags,
  };
}

/**
 * Tree node type for building folder hierarchy
 */
export interface FolderTreeNode extends ParsedCorpusFolderType {
  children: FolderTreeNode[];
}

/**
 * Build folder tree from flat list of folders
 */
export function buildFolderTree(folders: CorpusFolderType[]): FolderTreeNode[] {
  // Parse tags and initialize children arrays
  const parsedFolders: FolderTreeNode[] = folders.map((folder) => ({
    ...parseCorpusFolderTags(folder),
    children: [],
  }));

  const folderMap = new Map<string, FolderTreeNode>();
  const rootFolders: FolderTreeNode[] = [];

  // Build map
  parsedFolders.forEach((folder) => {
    folderMap.set(folder.id, folder);
  });

  // Build tree structure
  parsedFolders.forEach((folder) => {
    if (folder.parent) {
      const parentNode = folderMap.get(folder.parent.id);
      if (parentNode) {
        parentNode.children.push(folder);
      } else {
        // Parent not in list, treat as root
        rootFolders.push(folder);
      }
    } else {
      rootFolders.push(folder);
    }
  });

  return rootFolders;
}

/**
 * Build breadcrumb path from root to folder
 */
export function buildFolderBreadcrumb(
  folderId: string | null,
  folders: CorpusFolderType[]
): ParsedCorpusFolderType[] {
  if (!folderId) return [];

  const folderMap = new Map(folders.map((f) => [f.id, f]));
  const path: ParsedCorpusFolderType[] = [];

  let current = folderMap.get(folderId);
  while (current) {
    path.unshift(parseCorpusFolderTags(current));
    current = current.parent ? folderMap.get(current.parent.id) : undefined;
  }

  return path;
}

/**
 * Get all descendant folder IDs (for finding documents in subfolders)
 */
export function getAllDescendantFolderIds(
  folderId: string,
  folders: CorpusFolderType[]
): string[] {
  const folderMap = new Map(folders.map((f) => [f.id, f]));
  const descendants: string[] = [];

  function collectDescendants(id: string) {
    const children = folders.filter((f) => f.parent?.id === id);
    children.forEach((child) => {
      descendants.push(child.id);
      collectDescendants(child.id);
    });
  }

  collectDescendants(folderId);
  return descendants;
}
