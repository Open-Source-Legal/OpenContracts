import { atom } from "jotai";
import { ConversationType, ChatMessageType } from "../types/graphql-api";

// ============================================================================
// THREAD LIST STATE
// ============================================================================

export type ThreadSortOption = "newest" | "active" | "upvoted" | "pinned";
export type ThreadFilterOptions = {
  showLocked: boolean;
  showDeleted: boolean; // Only relevant for moderators
};

/**
 * Currently selected corpus for thread view
 */
export const selectedCorpusIdAtom = atom<string | null>(null);

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
 * Currently viewing thread ID
 */
export const currentThreadIdAtom = atom<string | null>(null);

/**
 * Currently selected message (for deep linking and highlighting)
 */
export const selectedMessageIdAtom = atom<string | null>(null);

/**
 * Message tree expansion state (for collapsible threads in future)
 */
export const expandedMessageIdsAtom = atom<Set<string>>(new Set<string>());

// ============================================================================
// UI STATE
// ============================================================================

/**
 * Show/hide thread creation modal
 */
export const showCreateThreadModalAtom = atom<boolean>(false);

/**
 * Show/hide reply form for specific message
 * Stores the message ID that user is replying to
 */
export const replyingToMessageIdAtom = atom<string | null>(null);

/**
 * Editing message (for edit functionality in future)
 */
export const editingMessageIdAtom = atom<string | null>(null);

// ============================================================================
// DERIVED ATOMS
// ============================================================================

/**
 * Computes whether current user can create threads in selected corpus
 * This will be implemented later with actual permission checks
 */
export const canCreateThreadAtom = atom<boolean>((get) => {
  // TODO: Implement permission checking from Apollo cache
  // For now, return true as placeholder
  return true;
});
