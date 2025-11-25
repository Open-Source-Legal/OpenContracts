/**
 * Thread components for discussion/forum functionality
 * Part of Issue #573: Thread List and Detail Views
 * Extended in Issue #574: Message Composer and Reply UI
 */

// Main container components
export { ThreadList } from "./ThreadList";
export { ThreadDetail } from "./ThreadDetail";

// List components
export { ThreadListItem } from "./ThreadListItem";
export { ThreadSortDropdown } from "./ThreadSortDropdown";
export { ThreadFilterToggles } from "./ThreadFilterToggles";
export { CreateThreadButton } from "./CreateThreadButton";

// Message components
export { MessageItem } from "./MessageItem";
export { MessageTree } from "./MessageTree";

// Composition and reply (Issue #574)
export { MessageComposer } from "./MessageComposer";
export { CreateThreadForm } from "./CreateThreadForm";
export { ReplyForm } from "./ReplyForm";

// Voting and reputation (Issue #575)
export { VoteButtons } from "./VoteButtons";
export { ReputationBadge } from "./ReputationBadge";
export { ReputationDisplay } from "./ReputationDisplay";
export { UserProfileReputation } from "./UserProfileReputation";

// Moderation (Issue #576)
export { ModerationControls } from "./ModerationControls";
export { ModeratorBadge } from "./ModeratorBadge";

// Utility components
export { ThreadBadge } from "./ThreadBadge";
export { RelativeTime } from "./RelativeTime";

// Utilities and types
export {
  buildMessageTree,
  flattenMessageTree,
  findMessageInTree,
} from "./utils";
export type { MessageNode } from "./utils";

// Hooks
export { useThreadPreferences } from "./hooks/useThreadPreferences";
export type { ThreadPreferences } from "./hooks/useThreadPreferences";
export { useMentionUsers } from "./hooks/useMentionUsers";

// Component prop types (Issue #574)
export type { MessageComposerProps } from "./MessageComposer";
export type { CreateThreadFormProps } from "./CreateThreadForm";
export type { ReplyFormProps } from "./ReplyForm";

// Component prop types (Issue #575)
export type { VoteButtonsProps } from "./VoteButtons";
export type {
  ReputationBadgeProps,
  ReputationBreakdown,
} from "./ReputationBadge";
export type { ReputationDisplayProps } from "./ReputationDisplay";
export type { UserProfileReputationProps } from "./UserProfileReputation";

// Component prop types (Issue #576)
export type { ModerationControlsProps } from "./ModerationControls";
export type { ModeratorBadgeProps } from "./ModeratorBadge";

// Component prop types (UI Controls)
export type { ThreadSortDropdownProps } from "./ThreadSortDropdown";
export type { ThreadFilterTogglesProps } from "./ThreadFilterToggles";
export type { CreateThreadButtonProps } from "./CreateThreadButton";

// Mention support
export { MentionPicker } from "./MentionPicker";
export type {
  MentionPickerProps,
  MentionUser,
  MentionPickerRef,
} from "./MentionPicker";
