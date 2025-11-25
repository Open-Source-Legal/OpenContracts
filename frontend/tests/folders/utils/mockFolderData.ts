import { CorpusFolderType } from "../../../src/graphql/queries/folders";

/**
 * Mock folder data factory for testing
 */

interface MockFolderOptions {
  id?: string;
  name?: string;
  description?: string;
  color?: string;
  icon?: string;
  tags?: string[];
  path?: string;
  documentCount?: number;
  descendantDocumentCount?: number;
  parent?: { id: string; name: string } | null;
  myPermissions?: string[];
  isPublished?: boolean;
}

export function createMockFolder(
  options: MockFolderOptions = {}
): CorpusFolderType {
  const id = options.id || `folder-${Math.random().toString(36).substr(2, 9)}`;
  const name = options.name || "Test Folder";

  return {
    id,
    name,
    description: options.description || "",
    color: options.color || "#05313d",
    icon: options.icon || "folder",
    tags: options.tags || [],
    path: options.path || name,
    documentCount: options.documentCount ?? 0,
    descendantDocumentCount: options.descendantDocumentCount ?? 0,
    parent: options.parent || null,
    corpus: {
      id: "corpus-1",
      title: "Test Corpus",
    },
    myPermissions: options.myPermissions || [
      "read",
      "update_corpus",
      "delete_corpus",
    ],
    isPublished: options.isPublished ?? false,
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
  };
}

/**
 * Create a hierarchical folder structure for testing
 */
export function createMockFolderHierarchy() {
  const rootFolder1 = createMockFolder({
    id: "folder-1",
    name: "Documents",
    path: "Documents",
    documentCount: 5,
    descendantDocumentCount: 15,
  });

  const childFolder1_1 = createMockFolder({
    id: "folder-1-1",
    name: "Legal",
    path: "Documents / Legal",
    parent: { id: rootFolder1.id, name: rootFolder1.name },
    documentCount: 3,
    descendantDocumentCount: 3,
  });

  const childFolder1_2 = createMockFolder({
    id: "folder-1-2",
    name: "Contracts",
    path: "Documents / Contracts",
    parent: { id: rootFolder1.id, name: rootFolder1.name },
    documentCount: 7,
    descendantDocumentCount: 10,
  });

  const grandchildFolder1_2_1 = createMockFolder({
    id: "folder-1-2-1",
    name: "2024",
    path: "Documents / Contracts / 2024",
    parent: { id: childFolder1_2.id, name: childFolder1_2.name },
    documentCount: 3,
    descendantDocumentCount: 3,
  });

  const rootFolder2 = createMockFolder({
    id: "folder-2",
    name: "Research",
    path: "Research",
    documentCount: 8,
    descendantDocumentCount: 8,
  });

  return {
    rootFolder1,
    childFolder1_1,
    childFolder1_2,
    grandchildFolder1_2_1,
    rootFolder2,
    allFolders: [
      rootFolder1,
      childFolder1_1,
      childFolder1_2,
      grandchildFolder1_2_1,
      rootFolder2,
    ],
  };
}

/**
 * Create deep folder hierarchy for testing breadcrumb ellipsis
 */
export function createDeepFolderHierarchy() {
  const folders: CorpusFolderType[] = [];
  let parent: { id: string; name: string } | null = null;
  let pathParts: string[] = [];

  for (let i = 1; i <= 10; i++) {
    const name = `Level ${i}`;
    pathParts.push(name);
    const folder = createMockFolder({
      id: `folder-deep-${i}`,
      name,
      path: pathParts.join(" / "),
      parent,
      documentCount: i,
    });
    folders.push(folder);
    parent = { id: folder.id, name: folder.name };
  }

  return {
    deepestFolder: folders[folders.length - 1],
    allFolders: folders,
  };
}
