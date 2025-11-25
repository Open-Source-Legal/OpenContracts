import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
  RelationGroup,
} from "../../../annotator/types/annotations";
import { TextSearchTokenResult, TextSearchSpanResult } from "../../../types";

/**
 * Type definitions for the unified content feed system
 */

export type ContentItemType = "note" | "annotation" | "relationship" | "search";

export interface Note {
  id: string;
  title?: string;
  content: string;
  creator: {
    email: string;
  };
  created: string;
}

export interface UnifiedContentItem {
  /** Unique identifier for the item in the feed */
  id: string;
  /** The type of content */
  type: ContentItemType;
  /** Page number for sorting (notes default to page 1) */
  pageNumber: number;
  /** The actual data for the item */
  data:
    | Note
    | ServerSpanAnnotation
    | ServerTokenAnnotation
    | RelationGroup
    | TextSearchTokenResult
    | TextSearchSpanResult;
  /** Timestamp for secondary sorting */
  timestamp?: Date;
}

export interface ContentFilters {
  /** Which content types to show */
  contentTypes: Set<ContentItemType>;
  /** Additional filters per content type */
  annotationFilters?: {
    labels?: Set<string>;
    showStructural?: boolean;
  };
  relationshipFilters?: {
    showStructural?: boolean;
  };
  /** Text search within the feed */
  searchQuery?: string;
}

export type SortOption = "page" | "type" | "date";

export interface UnifiedFeedState {
  /** Current active filters */
  filters: ContentFilters;
  /** Current sort option */
  sortBy: SortOption;
  /** Whether feed is loading */
  isLoading: boolean;
}

export interface SidebarViewMode {
  mode: "chat" | "feed" | "extract" | "analysis" | "discussions";
}
