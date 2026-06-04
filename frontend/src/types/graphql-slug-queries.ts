import { CorpusType, DocumentType, UserType } from "./graphql-api";

/**
 * TypeScript interfaces for slug resolution GraphQL queries
 */

// User by slug
export interface UserBySlugQuery {
  userBySlug: Pick<UserType, "id" | "slug" | "username"> | null;
}

export interface UserBySlugVariables {
  slug: string;
}

// Corpus by slugs
export interface CorpusBySlugQuery {
  corpusBySlugs: Pick<CorpusType, "id" | "slug" | "title"> | null;
}

export interface CorpusBySlugsVariables {
  userSlug: string;
  corpusSlug: string;
}

// Document by slugs
export interface DocumentBySlugQuery {
  documentBySlugs: Pick<DocumentType, "id" | "slug" | "title"> | null;
}

export interface DocumentBySlugsVariables {
  userSlug: string;
  documentSlug: string;
}

// Document in corpus by slugs
export interface DocumentInCorpusBySlugQuery {
  documentInCorpusBySlugs: Pick<DocumentType, "id" | "slug" | "title"> | null;
}

export interface DocumentInCorpusBySlugsVariables {
  userSlug: string;
  corpusSlug: string;
  documentSlug: string;
}

// Full resolution queries
export interface ResolveCorpusFullQuery {
  corpusBySlugs: {
    id: string;
    slug: string | null;
    title: string;
    description: string;
    isPublic: boolean;
    isPersonal?: boolean;
    creator: {
      id: string;
      username: string;
      slug: string | null;
    };
    labelSet: {
      id: string;
      title: string;
    } | null;
    documentCount: number | null;
    annotationCount: number | null;
  } | null;
}

export interface ResolveCorpusFullVariables {
  userSlug: string;
  corpusSlug: string;
}

export interface ResolveDocumentFullQuery {
  documentBySlugs: {
    id: string;
    slug: string | null;
    title: string;
    description: string;
    fileType: string;
    isPublic: boolean;
    pdfFile: string | null;
    backendLock: boolean;
    creator: {
      id: string;
      username: string;
      slug: string | null;
    };
  } | null;
}

export interface ResolveDocumentFullVariables {
  userSlug: string;
  documentSlug: string;
}

export interface ResolveDocumentInCorpusFullQuery {
  corpusBySlugs: ResolveCorpusFullQuery["corpusBySlugs"];
  documentInCorpusBySlugs: {
    id: string;
    slug: string | null;
    title: string;
    description: string;
    fileType: string;
    isPublic: boolean;
    pdfFile: string | null;
    backendLock: boolean;
    isLatestVersion: boolean;
    creator: {
      id: string;
      username: string;
      slug: string | null;
    };
  } | null;
}

export interface ResolveDocumentInCorpusFullVariables {
  userSlug: string;
  corpusSlug: string;
  documentSlug: string;
  versionNumber?: number | null;
}
