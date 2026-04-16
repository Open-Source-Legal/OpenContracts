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

export type Page = {
  index: number;
  width: number;
  height: number;
};

export type PageTokens = {
  page: Page;
  tokens: Token[];
};

export interface Token {
  x: number;
  y: number;
  height: number;
  width: number;
  text: string;
  // Image token fields (optional - only present for image tokens)
  is_image?: boolean;
  image_path?: string;
  base64_data?: string;
  format?: string;
  content_hash?: string;
  original_width?: number;
  original_height?: number;
  image_type?: string;
  token_index?: number;
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
