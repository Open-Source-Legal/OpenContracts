import React from "react";
import { MessageBadges } from "../../src/components/badges/MessageBadges";
import { ChatMessageType, UserBadgeType } from "../../src/types/graphql-api";

/**
 * Recreates the sidebar's clipping chain (a narrow flex column with
 * `overflow: hidden`) so the badge tooltip's portal can be exercised
 * without booting the full thread-detail view + GraphQL stack.
 *
 * The badge is intentionally placed near the very top of the frame —
 * pre-fix, the absolutely-positioned tooltip would be clipped by the
 * frame's `overflow: hidden`; post-fix, it's portalled to document.body
 * and flips below the badge when there isn't room above.
 */
export function BadgeClipHarness() {
  const message: ChatMessageType = {
    id: "msg-1",
    content: "What do y'all think?",
    msgType: "HUMAN",
  } as unknown as ChatMessageType;

  const userBadges: UserBadgeType[] = [
    {
      id: "ub-1",
      awardedAt: "2026-05-22T10:00:00Z",
      user: {
        id: "user-1",
        username: "majesticGrasshopper",
      },
      badge: {
        id: "badge-1",
        name: "Conversationalist",
        description: "Awarded for sparking lively threads in this corpus.",
        icon: "MessageCircle",
        color: "#2563eb",
        badgeType: "GLOBAL",
      },
      awardedBy: null,
      corpus: null,
    } as unknown as UserBadgeType,
  ];

  return (
    <div
      data-testid="clip-frame"
      style={{
        width: 360,
        height: 560,
        overflow: "hidden",
        border: "1px solid #e5e7eb",
        background: "#fafbfc",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Mock "Back to List" header to match the sidebar context */}
      <div
        style={{
          padding: "0.75rem 1rem",
          borderBottom: "1px solid #e5e7eb",
          background: "#f3f4f6",
          fontSize: "0.8125rem",
          color: "#475569",
        }}
      >
        ← Back to List
      </div>
      <div
        style={{
          padding: "0.5rem 1rem",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          background: "white",
        }}
      >
        <strong style={{ fontSize: "0.875rem", color: "#0f172a" }}>
          majesticGrasshopper
        </strong>
        <MessageBadges
          message={message}
          userBadges={userBadges}
          maxBadges={2}
          showTooltip={true}
        />
      </div>
    </div>
  );
}
