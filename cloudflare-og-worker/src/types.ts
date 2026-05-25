/**
 * TypeScript types for cite OG Preview Worker
 */

/**
 * Cloudflare Worker environment bindings
 */
export interface Env {
  /** Base URL of the cite site */
  SITE_URL: string;
  /** Backend API URL for GraphQL queries */
  API_URL: string;
  /** Base URL for static OG preview images */
  OG_IMAGE_BASE: string;
}

/**
 * Entity types that support deep-linking
 */
export type EntityType =
  | "corpus"
  | "document"
  | "document_in_corpus"
  | "extract"
  | "thread";

/**
 * Parsed route information from URL pathname
 */
export interface ParsedRoute {
  type: EntityType;
  userSlug: string;
  corpusSlug?: string;
  documentSlug?: string;
  extractId?: string;
  threadId?: string;
}

/**
 * Labeled data pair for Twitter structured card previews
 */
export interface LabeledData {
  label: string;
  value: string;
}

/**
 * Open Graph metadata for social media previews
 */
export interface OGMetadata {
  title: string;
  description: string;
  image: string | null;
  type: EntityType;
  entityName: string;
  creatorName: string;
  documentCount?: number;
  corpusTitle?: string;
  /** Structured key-value pairs for Twitter summary cards */
  labeledData?: LabeledData[];
}

/**
 * GraphQL response structure
 */
export interface GraphQLResponse<T = Record<string, unknown>> {
  data: T;
  errors?: Array<{
    message: string;
    locations?: Array<{ line: number; column: number }>;
    path?: Array<string | number>;
  }>;
}

/**
 * OG Corpus metadata from GraphQL
 */
export interface OGCorpusData {
  ogCorpusMetadata: {
    title: string;
    description: string;
    iconUrl: string | null;
    documentCount: number;
    creatorName: string;
    isPublic: boolean;
  } | null;
}

/**
 * OG Document metadata from GraphQL
 */
export interface OGDocumentData {
  ogDocumentMetadata: {
    title: string;
    description: string;
    iconUrl: string | null;
    corpusTitle: string | null;
    corpusDescription: string | null;
    creatorName: string;
    isPublic: boolean;
  } | null;
}

/**
 * OG Thread metadata from GraphQL
 */
export interface OGThreadData {
  ogThreadMetadata: {
    title: string;
    corpusTitle: string;
    messageCount: number;
    creatorName: string;
    isPublic: boolean;
  } | null;
}

/**
 * OG Extract metadata from GraphQL
 */
export interface OGExtractData {
  ogExtractMetadata: {
    name: string;
    corpusTitle: string;
    fieldsetName: string;
    creatorName: string;
    isPublic: boolean;
  } | null;
}
