import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

// ============================================================================
// THREAD LIST STATE
// ============================================================================

export type ThreadSortOption = "newest" | "active" | "upvoted" | "pinned";
type ThreadFilterOptions = {
  showLocked: boolean;
  showDeleted: boolean; // Only relevant for moderators
};

/**
 * Thread list sort order
 * Default: "pinned" to show pinned threads first
 */
export const threadSortAtom = atom<ThreadSortOption>("pinned");

/**
 * Thread list filters
 */
export const threadFiltersAtom = atom<ThreadFilterOptions>({
  showLocked: true,
  showDeleted: false,
});

// ============================================================================
// THREAD DETAIL STATE
// ============================================================================

/**
 * Currently selected message (for deep linking and highlighting)
 */
export const selectedMessageIdAtom = atom<string | null>(null);

// ============================================================================
// UI STATE
// ============================================================================

/**
 * Show/hide reply form for specific message
 * Stores the message ID that user is replying to
 */
export const replyingToMessageIdAtom = atom<string | null>(null);

// ============================================================================
// INLINE THREAD VIEW STATE
// ============================================================================

// Note: Inline thread selection in CorpusDiscussionsView is now URL-driven
// via the ?thread= query param, synced through CentralRouteManager to the
// selectedThreadId reactive var in graphql/cache.ts.

/**
 * Corpus context sidebar expanded state (persisted to localStorage)
 * Controls whether the sidebar is expanded or collapsed when viewing thread details
 */
export const threadContextSidebarExpandedAtom = atomWithStorage(
  "threadContextSidebarExpanded",
  true
);
