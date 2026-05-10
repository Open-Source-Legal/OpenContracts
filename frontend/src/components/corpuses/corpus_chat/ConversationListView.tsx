import React, { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft,
  Calendar,
  MessageCircle,
  Plus,
  Search,
  X,
} from "lucide-react";

import {
  DatePickerExpanded,
  ExpandingInput,
  IconButton,
} from "../../knowledge_base/document/FilterContainers";
import { FetchMoreOnVisible } from "../../widgets/infinite_scroll/FetchMoreOnVisible";
import { getCreatorDisplay } from "../../../utils/userDisplay";

import {
  EnhancedFilterContainer,
  NewChatButton,
  ToolbarDivider,
  EnhancedConversationGrid,
  EnhancedConversationCard,
  ChatItemIcon,
  ChatItemContent,
  ChatItemTitle,
  ChatItemMeta,
  MessageCountBadge,
  EmptyStateContainer,
  EmptyStateIcon,
  EmptyStateTitle,
  EmptyStateDescription,
  EmptyStateButton,
} from "./styles";

/**
 * Represents a single conversation node from the GraphQL query result.
 */
export interface ConversationNode {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  chatMessages: {
    totalCount: number;
  };
  // ``email`` is redacted to ``null`` for non-self viewers per the user
  // privacy contract — only ``id`` and ``slug`` are guaranteed.
  creator: {
    id?: string | null;
    slug?: string | null;
    email?: string | null;
  };
}

interface ConversationListViewProps {
  /** List of conversation nodes to render. */
  conversations: (ConversationNode | null | undefined)[];
  /** Callback to load an existing conversation by ID. */
  onLoadConversation: (conversationId: string) => void;
  /** Callback to start a new chat. */
  onStartNewChat: () => void;
  /** Callback to fetch more conversations for infinite scroll. */
  onFetchMore: () => void;
  /** Current title filter value (controlled). */
  titleFilter: string;
  /** Setter for the title filter. */
  onTitleFilterChange: (value: string) => void;
  /** Current "created after" date filter (controlled). */
  createdAtGte: string;
  /** Setter for createdAtGte. */
  onCreatedAtGteChange: (value: string) => void;
  /** Current "created before" date filter (controlled). */
  createdAtLte: string;
  /** Setter for createdAtLte. */
  onCreatedAtLteChange: (value: string) => void;
  /** Optional back callback (e.g. return to corpus home on mobile) */
  onBack?: () => void;
}

/**
 * ConversationListView renders the "conversation menu" view of CorpusChat.
 * It includes a filter toolbar (search, date filters, new chat button),
 * the scrollable grid of conversation cards with infinite scroll,
 * and an empty-state placeholder when no conversations exist.
 */
export const CorpusConversationListView: React.FC<
  ConversationListViewProps
> = ({
  conversations,
  onLoadConversation,
  onStartNewChat,
  onFetchMore,
  titleFilter,
  onTitleFilterChange,
  createdAtGte,
  onCreatedAtGteChange,
  createdAtLte,
  onCreatedAtLteChange,
  onBack,
}) => {
  // Local UI state for toggling search / date picker visibility
  const [showSearch, setShowSearch] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const datePickerRef = useRef<HTMLDivElement>(null);

  return (
    <motion.div
      key="conversation-menu"
      style={{
        width: "100%",
        height: "100%",
        maxHeight: "100%",
        display: "flex",
        flexDirection: "column",
        overflowY: "auto",
        flex: 1,
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <EnhancedFilterContainer>
        {onBack && (
          <>
            <IconButton
              onClick={onBack}
              whileTap={{ scale: 0.95 }}
              title="Back to Home"
              aria-label="Back"
            >
              <ArrowLeft />
            </IconButton>
            <ToolbarDivider />
          </>
        )}

        <NewChatButton
          onClick={onStartNewChat}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <Plus size={16} />
          <span>New Chat</span>
        </NewChatButton>

        <ToolbarDivider />

        <AnimatePresence>
          {showSearch && (
            <ExpandingInput
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: "auto", opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              ref={searchInputRef}
            >
              <input
                className="expanded"
                placeholder="Search chats..."
                value={titleFilter}
                onChange={(e) => onTitleFilterChange(e.target.value)}
                autoFocus
              />
            </ExpandingInput>
          )}
        </AnimatePresence>

        <IconButton
          onClick={() => setShowSearch(!showSearch)}
          $isActive={!!titleFilter}
          whileTap={{ scale: 0.95 }}
          title="Search"
        >
          <Search />
        </IconButton>

        <IconButton
          onClick={() => setShowDatePicker(!showDatePicker)}
          $isActive={!!(createdAtGte || createdAtLte)}
          whileTap={{ scale: 0.95 }}
          title="Filter by date"
        >
          <Calendar />
        </IconButton>

        <AnimatePresence>
          {showDatePicker && (
            <DatePickerExpanded
              ref={datePickerRef}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <input
                type="date"
                value={createdAtGte}
                onChange={(e) => onCreatedAtGteChange(e.target.value)}
                placeholder="Start Date"
              />
              <input
                type="date"
                value={createdAtLte}
                onChange={(e) => onCreatedAtLteChange(e.target.value)}
                placeholder="End Date"
              />
            </DatePickerExpanded>
          )}
        </AnimatePresence>

        {(titleFilter || createdAtGte || createdAtLte) && (
          <IconButton
            onClick={() => {
              onTitleFilterChange("");
              onCreatedAtGteChange("");
              onCreatedAtLteChange("");
              setShowSearch(false);
              setShowDatePicker(false);
            }}
            whileTap={{ scale: 0.95 }}
          >
            <X />
          </IconButton>
        )}
      </EnhancedFilterContainer>

      {conversations.length > 0 ? (
        <EnhancedConversationGrid id="conversation-grid">
          {conversations.map((conv, index) => {
            if (!conv) return null;
            const messageCount = conv.chatMessages?.totalCount || 0;
            return (
              <EnhancedConversationCard
                key={conv.id}
                onClick={() => onLoadConversation(conv.id)}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{
                  duration: 0.2,
                  delay: index * 0.03,
                }}
              >
                <ChatItemIcon>
                  <MessageCircle />
                </ChatItemIcon>
                <ChatItemContent>
                  <ChatItemTitle>{conv.title || "Untitled Chat"}</ChatItemTitle>
                  <ChatItemMeta>
                    <span>
                      {formatDistanceToNow(new Date(conv.createdAt))} ago
                    </span>
                    {conv.creator && (
                      <>
                        <span>·</span>
                        <span>{getCreatorDisplay(conv.creator)}</span>
                      </>
                    )}
                  </ChatItemMeta>
                </ChatItemContent>
                {messageCount > 0 && (
                  <MessageCountBadge>{messageCount}</MessageCountBadge>
                )}
              </EnhancedConversationCard>
            );
          })}
          <FetchMoreOnVisible fetchNextPage={onFetchMore} />
        </EnhancedConversationGrid>
      ) : (
        <EmptyStateContainer>
          <EmptyStateIcon>
            <MessageCircle />
          </EmptyStateIcon>
          <EmptyStateTitle>No chats yet</EmptyStateTitle>
          <EmptyStateDescription>
            Start a conversation with the AI to ask questions about this corpus.
          </EmptyStateDescription>
          <EmptyStateButton
            onClick={onStartNewChat}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Plus size={18} />
            Start New Chat
          </EmptyStateButton>
        </EmptyStateContainer>
      )}
    </motion.div>
  );
};
