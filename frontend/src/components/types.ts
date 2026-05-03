import { ReactElement } from "react";
import { AnnotationLabelType } from "../types/graphql-api";
import { PDFPageInfo } from "./annotator/types/pdf";

/**
 *  Types
 */

export enum ExportTypes {
  OPEN_CONTRACTS = "OPEN_CONTRACTS",
  FUNSD = "FUNSD",
}

export enum PermissionTypes {
  CAN_PERMISSION = "CAN_PERMISSION",
  CAN_PUBLISH = "CAN_PUBLISH",
  CAN_COMMENT = "CAN_COMMENT",
  CAN_CREATE = "CAN_CREATE",
  CAN_READ = "CAN_READ",
  CAN_UPDATE = "CAN_UPDATE",
  CAN_REMOVE = "CAN_REMOVE",
}

export enum ViewState {
  LOADING,
  LOADED,
  NOT_FOUND,
  ERROR,
}

/**
 * Compact (v2-derived) image metadata.
 *
 * Mirrors the `CompactImageMetaType` short keys used on the backend wire
 * format. Always carried inside a {@link CompactToken} via `imageMeta`.
 *
 * | wire key | meaning          |
 * | -------- | ---------------- |
 * | `p`      | image_path       |
 * | `b64`    | base64_data      |
 * | `f`      | format           |
 * | `ch`     | content_hash     |
 * | `ow`     | original_width   |
 * | `oh`     | original_height  |
 * | `it`     | image_type       |
 */
export interface CompactImageMeta {
  p?: string;
  b64?: string;
  f?: string;
  ch?: string;
  ow?: number;
  oh?: number;
  it?: string;
}

/**
 * Canonical in-memory PAWLs token (v2-derived).
 *
 * This is the only token shape the frontend runtime works with after
 * decode. The wire format (v1 dict tokens or v2 positional arrays) is
 * normalized to this shape inside `utils/compactPawls.ts` — every other
 * consumer reads {@link CompactToken}.
 *
 * Field names remain PDF-semantic (`x`, `y`, `width`, `height`, `text`)
 * because they describe the runtime geometry, not the wire encoding.
 * `isImage` is always set (camelCase, no `is_image`); image-specific
 * metadata lives on `imageMeta` using the v2 short keys.
 */
export interface CompactToken {
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  /** True iff this token is an image (v2: had a 6th metadata element). */
  isImage: boolean;
  /** Compact image metadata (short keys). Undefined for text tokens. */
  imageMeta?: CompactImageMeta;
}

/**
 * Canonical in-memory PAWLs page (v2-derived).
 *
 * Replaces the old `PageTokens` + `Page` pair. The `index` field is
 * materialized for ergonomic consumer access (the wire format relies on
 * implicit array position).
 */
export interface CompactPage {
  index: number;
  width: number;
  height: number;
  tokens: CompactToken[];
}

export interface LabelSet {
  id: string;
  title: string;
  icon: string;
  allAnnotationLabels: AnnotationLabelType[];
  description?: string;
}

export interface LooseObject {
  [key: string]: any;
}

export type EditMode = "EDIT" | "VIEW" | "CREATE";

export interface CRUDProps {
  mode: EditMode;
  modelName: string;
  hasFile: boolean;
  fileField: string;
  fileLabel: string;
  fileIsImage: boolean;
  acceptedFileTypes: string;
}

// Define a more flexible prop type for property widgets
interface PropertyWidgetProps<T = any> {
  onChange: (updatedFields: Record<string, T>) => void;
  [key: string]: any; // Allow any additional props
}

// Define a type for the propertyWidgets prop
export type PropertyWidgets = {
  [key: string]: React.ReactElement<PropertyWidgetProps>;
};

export type BoundingBox = {
  top: number;
  bottom: number;
  left: number;
  right: number;
};

export type TokenId = {
  pageIndex: number;
  tokenIndex: number;
};

export type SpanAnnotationJson = {
  start: number;
  end: number;
};

export type SinglePageAnnotationJson = {
  bounds: BoundingBox;
  tokensJsons: TokenId[];
  rawText: string;
};

export type TextSearchTokenResult = {
  id: number;
  tokens: Record<number, TokenId[]>;
  bounds?: Record<number, BoundingBox>;
  fullContext: ReactElement | null;
  start_page: number;
  end_page: number;
};

export type TextSearchSpanResult = {
  id: number;
  start_index: number;
  end_index: number;
  fullContext: ReactElement | null;
  text: string;
};

export type MultipageAnnotationJson = Record<number, SinglePageAnnotationJson>;

// Compact v2 types — canonical definitions in utils/compactAnnotationJson.ts
export type {
  CompactPageData,
  CompactAnnotationJson,
} from "../utils/compactAnnotationJson";

export interface PageProps {
  pageInfo: PDFPageInfo;
  read_only: boolean;
  onError: (_err: Error) => void;
}
