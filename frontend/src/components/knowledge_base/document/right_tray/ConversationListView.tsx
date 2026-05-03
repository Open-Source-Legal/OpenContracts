/**
 * ConversationListView
 *
 * Renders the conversation list (filter toolbar, conversation cards grid,
 * new-chat FAB, and empty state). Extracted from ChatTray to keep the main
 * component focused on the active chat session.
 */

import React from "react";
import { formatDistanceToNow } from "date-fns";
import { AnimatePresence, motion } from "framer-motion";
import { Calendar, MessageSquare, Plus, Search, X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  CardContent,
  CardTitle,
  ConversationCard,
  ConversationGrid,
  Creator,
  MessageCount,
  TimeStamp,
  NewChatFloatingButton,
} from "../ChatContainers";
import {
  DatePickerExpanded,
  ExpandingInput,
  FilterContainer,
  IconButton,
} from "../FilterContainers";
import { FetchMoreOnVisible } from "../../../widgets/infinite_scroll/FetchMoreOnVisible";
import { calculateMessageStats, getMessageCountColor } from "./chatUtils";
import type { ConversationType } from "../../../../types/graphql-api";

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface ConversationListViewProps {
  /** Resolved conversation nodes to display. */
  conversations: Array<ConversationType | null | undefined>;

  /* --- Filter state --- */
  showSearch: boolean;
  setShowSearch: React.Dispatch<React.SetStateAction<boolean>>;
  showDatePicker: boolean;
  setShowDatePicker: React.Dispatch<React.SetStateAction<boolean>>;
  titleFilter: string;
  setTitleFilter: React.Dispatch<React.SetStateAction<string>>;
  createdAtGte: string;
  setCreatedAtGte: React.Dispatch<React.SetStateAction<string>>;
  createdAtLte: string;
  setCreatedAtLte: React.Dispatch<React.SetStateAction<string>>;

  /* --- Refs for click-outside dismiss --- */
  searchInputRef: React.RefObject<HTMLElement | null>;
  datePickerRef: React.RefObject<HTMLElement | null>;

  /* --- Handlers --- */
  loadConversation: (conversationId: string) => void;
  handleFetchMoreConversations: () => void;
  startNewChat: () => void;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export const DocumentConversationListView: React.FC<
  ConversationListViewProps
> = ({
  conversations,
  showSearch,
  setShowSearch,
  showDatePicker,
  setShowDatePicker,
  titleFilter,
  setTitleFilter,
  createdAtGte,
  setCreatedAtGte,
  createdAtLte,
  setCreatedAtLte,
  searchInputRef,
  datePickerRef,
  loadConversation,
  handleFetchMoreConversations,
  startNewChat,
}) => {
  return (
    <motion.div
      id="conversation-menu"
      style={{
        flex: 1,
        minHeight: 0,
        width: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "stretch",
        gap: "0.5rem",
        position: "relative",
        overflow: "hidden",
      }}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <FilterContainer>
        <AnimatePresence>
          {showSearch && (
            <ExpandingInput
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: "auto", opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              ref={searchInputRef as React.Ref<HTMLDivElement>}
            >
              <input
                className="expanded"
                placeholder="Search by title..."
                value={titleFilter}
                onChange={(e) => setTitleFilter(e.target.value)}
                autoFocus
              />
            </ExpandingInput>
          )}
        </AnimatePresence>

        <IconButton
          onClick={() => setShowSearch(!showSearch)}
          $isActive={!!titleFilter}
          whileTap={{ scale: 0.95 }}
          data-testid="search-filter-button"
        >
          <Search />
        </IconButton>

        <IconButton
          onClick={() => setShowDatePicker(!showDatePicker)}
          $isActive={!!(createdAtGte || createdAtLte)}
          whileTap={{ scale: 0.95 }}
          data-testid="date-filter-button"
        >
          <Calendar />
        </IconButton>

        <AnimatePresence>
          {showDatePicker && (
            <DatePickerExpanded
              ref={datePickerRef as React.Ref<HTMLDivElement>}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              <input
                type="date"
                value={createdAtGte}
                onChange={(e) => setCreatedAtGte(e.target.value)}
                placeholder="Start Date"
              />
              <input
                type="date"
                value={createdAtLte}
                onChange={(e) => setCreatedAtLte(e.target.value)}
                placeholder="End Date"
              />
            </DatePickerExpanded>
          )}
        </AnimatePresence>

        {(titleFilter || createdAtGte || createdAtLte) && (
          <IconButton
            onClick={() => {
              setTitleFilter("");
              setCreatedAtGte("");
              setCreatedAtLte("");
              setShowSearch(false);
              setShowDatePicker(false);
            }}
            whileTap={{ scale: 0.95 }}
            data-testid="clear-filters-button"
          >
            <X />
          </IconButton>
        )}
      </FilterContainer>

      <ConversationGrid id="conversation-grid">
        {conversations.length === 0 && (
          <motion.div
            data-testid="conversations-empty-state"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: 0.05 }}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              padding: "3rem 1.5rem 6rem",
              gap: "0.75rem",
              color: OS_LEGAL_COLORS.textSecondary,
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: `${OS_LEGAL_COLORS.blueSurface}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: OS_LEGAL_COLORS.primaryBlue,
              }}
            >
              <MessageSquare size={26} />
            </div>
            <div
              style={{
                fontSize: "1rem",
                fontWeight: 600,
                color: OS_LEGAL_COLORS.textPrimary,
              }}
            >
              No conversations yet
            </div>
            <div style={{ fontSize: "0.875rem", maxWidth: 320 }}>
              Start a new chat to ask questions about this document. Past
              conversations will appear here.
            </div>
          </motion.div>
        )}
        {conversations.map((conv, index) => {
          if (!conv) return null;
          return (
            <ConversationCard
              key={conv.id}
              data-testid={`conversation-card-${conv.id}`}
              onClick={() => loadConversation(conv.id)}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.3,
                delay: index * 0.05,
                ease: [0.4, 0, 0.2, 1],
              }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <MessageCount
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{
                  type: "spring",
                  stiffness: 500,
                  damping: 25,
                  delay: index * 0.05 + 0.2,
                }}
                $colorStyle={getMessageCountColor(
                  conv.chatMessages?.totalCount || 0,
                  calculateMessageStats(conversations as any[])
                )}
              >
                {conv.chatMessages?.totalCount || 0}
              </MessageCount>
              <CardContent>
                <CardTitle>{conv.title || "Untitled Conversation"}</CardTitle>
                <div
                  style={{
                    color: OS_LEGAL_COLORS.textSecondary,
                    fontSize: "0.875rem",
                  }}
                >
                  <TimeStamp>
                    {formatDistanceToNow(new Date(conv.createdAt))} ago
                  </TimeStamp>
                  <Creator>{conv.creator?.email}</Creator>
                </div>
              </CardContent>
            </ConversationCard>
          );
        })}
        <FetchMoreOnVisible fetchNextPage={handleFetchMoreConversations} />
      </ConversationGrid>

      <NewChatFloatingButton
        onClick={() => startNewChat()}
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0, opacity: 0 }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        data-testid="new-chat-button"
      >
        <Plus />
      </NewChatFloatingButton>
    </motion.div>
  );
};
