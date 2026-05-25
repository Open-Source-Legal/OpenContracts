/**
 * Lightweight up/down arrow + score widget used on corpus cards in the
 * Corpus list view.  Mirrors the message-vote widget in
 * ``../threads/VoteButtons.tsx`` but is intentionally:
 *
 *   - **smaller** (designed to sit as an overlay pill on a card),
 *   - **anonymous-friendly** (the backend mutation accepts both auth and
 *     anon callers; the widget no-ops only on self-vote / disabled state),
 *   - **single-component** (no separate up/down/remove props — toggle is
 *     handled internally based on the viewer's current ``myVote``).
 *
 * Cache update strategy: the mutation response already carries the
 * refreshed ``upvoteCount`` / ``downvoteCount`` / ``score`` / ``myVote``,
 * so we use the standard Apollo ``cache.modify`` pattern keyed by the
 * CorpusType node id.  This keeps every corpus card on screen in sync
 * after a vote without a full refetch.
 */

import React, { useCallback, useState } from "react";
import { ApolloCache, useMutation, useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { ChevronUp, ChevronDown } from "lucide-react";
import { toast } from "react-toastify";

import {
  DOWNVOTE_CORPUS,
  DownvoteCorpusOutput,
  REMOVE_CORPUS_VOTE,
  RemoveCorpusVoteInput,
  RemoveCorpusVoteOutput,
  UPVOTE_CORPUS,
  UpvoteCorpusOutput,
  VoteCorpusInput,
  VoteCorpusResponse,
} from "../../graphql/mutations";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { backendUserObj } from "../../graphql/cache";

// --------------------------------------------------------------------------- //
// Styled chrome
// --------------------------------------------------------------------------- //

const Pill = styled.div<{ $vertical: boolean }>`
  display: inline-flex;
  flex-direction: ${({ $vertical }) => ($vertical ? "column" : "row")};
  align-items: center;
  gap: 2px;
  padding: ${({ $vertical }) => ($vertical ? "4px 2px" : "2px 4px")};
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 999px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
`;

const ArrowButton = styled.button<{
  $variant: "up" | "down";
  $active: boolean;
  $disabled: boolean;
}>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  background: ${({ $active, $variant }) =>
    $active
      ? $variant === "up"
        ? "rgba(16, 185, 129, 0.12)"
        : "rgba(239, 68, 68, 0.12)"
      : "transparent"};
  color: ${({ $active, $variant }) =>
    $active
      ? $variant === "up"
        ? "rgb(5, 150, 105)"
        : "rgb(220, 38, 38)"
      : OS_LEGAL_COLORS.textSecondary};
  border-radius: 999px;
  cursor: ${({ $disabled }) => ($disabled ? "not-allowed" : "pointer")};
  opacity: ${({ $disabled }) => ($disabled ? 0.5 : 1)};
  transition: background 0.12s, color 0.12s;

  &:hover {
    background: ${({ $disabled, $variant }) =>
      $disabled
        ? "transparent"
        : $variant === "up"
        ? "rgba(16, 185, 129, 0.18)"
        : "rgba(239, 68, 68, 0.18)"};
    color: ${({ $disabled, $variant }) =>
      $disabled
        ? OS_LEGAL_COLORS.textSecondary
        : $variant === "up"
        ? "rgb(5, 150, 105)"
        : "rgb(220, 38, 38)"};
  }
`;

const Score = styled.span<{ $score: number; $vertical: boolean }>`
  min-width: 18px;
  padding: ${({ $vertical }) => ($vertical ? "2px 0" : "0 4px")};
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  line-height: 1;
  color: ${({ $score }) =>
    $score > 0
      ? "rgb(5, 150, 105)"
      : $score < 0
      ? "rgb(220, 38, 38)"
      : OS_LEGAL_COLORS.textSecondary};
  user-select: none;
`;

// --------------------------------------------------------------------------- //
// Apollo cache helper
// --------------------------------------------------------------------------- //
//
// All three mutations return ``VoteCorpusResponse`` with the refreshed
// vote columns on ``obj``; mirror those into every CorpusType reference
// in the cache so cards on other screens (e.g. the corpus modal) stay in
// sync without a refetch.

function updateCorpusVoteCache(
  cache: ApolloCache<unknown>,
  response: VoteCorpusResponse | null | undefined
): void {
  if (!response?.obj) return;
  const { id, upvoteCount, downvoteCount, score, myVote } = response.obj;
  cache.modify({
    id: cache.identify({ __typename: "CorpusType", id }),
    fields: {
      upvoteCount: () => upvoteCount,
      downvoteCount: () => downvoteCount,
      score: () => score,
      myVote: () => myVote,
    },
  });
}

// --------------------------------------------------------------------------- //
// Component
// --------------------------------------------------------------------------- //

export interface CorpusVoteWidgetProps {
  /** Relay global id of the corpus being voted on. */
  corpusId: string;
  /** Server-side ``upvote_count - downvote_count`` (denormalized). */
  score: number;
  /** Server-side current vote: "UPVOTE", "DOWNVOTE", or null. */
  myVote: "UPVOTE" | "DOWNVOTE" | null | undefined;
  /** ID of the corpus creator (used to disable self-vote). */
  creatorId?: string;
  /** Test id appended to the root pill for Playwright targeting. */
  testId?: string;
  /** Smaller variant used on cards (default). Reserved for future expansion. */
  size?: "sm";
  /**
   * Pill layout. ``"horizontal"`` (default) lays the arrows side-by-side
   * with the score between them — used in flush, inline contexts. ``"vertical"``
   * stacks chevron-up / score / chevron-down — used as a Reddit-style rail
   * on corpus cards so the pill doesn't overlap the avatar.
   */
  orientation?: "horizontal" | "vertical";
}

export const CorpusVoteWidget = React.memo(function CorpusVoteWidget({
  corpusId,
  score,
  myVote,
  creatorId,
  testId,
  orientation = "horizontal",
}: CorpusVoteWidgetProps) {
  const isVertical = orientation === "vertical";
  const backendUser = useReactiveVar(backendUserObj);
  const isOwn = Boolean(
    backendUser?.id && creatorId && backendUser.id === creatorId
  );

  // Optimistic state — "UPVOTE", "DOWNVOTE", null (= no vote), or
  // ``undefined`` meaning "no override, use the server's ``myVote``".  We
  // store the *target* state rather than a delta so the optimistic score
  // calculation below is straightforward.
  const [optimisticVote, setOptimisticVote] = useState<
    "UPVOTE" | "DOWNVOTE" | null | undefined
  >(undefined);

  const effectiveVote: "UPVOTE" | "DOWNVOTE" | null =
    optimisticVote === undefined ? myVote ?? null : optimisticVote;

  // Optimistic score: start from the canonical server score, then undo
  // the user's prior vote (if any) and apply their new one.  Clamps to
  // integers; mirrors the calculation already used by VoteButtons.tsx so
  // both widgets render the same scoring rule.
  const displayScore = React.useMemo(() => {
    let value = score;
    const previous = myVote ?? null;
    const next = effectiveVote;
    if (previous === next) return value;
    if (previous === "UPVOTE") value -= 1;
    else if (previous === "DOWNVOTE") value += 1;
    if (next === "UPVOTE") value += 1;
    else if (next === "DOWNVOTE") value -= 1;
    return value;
  }, [score, myVote, effectiveVote]);

  const onMutationError = useCallback((err: unknown) => {
    setOptimisticVote(undefined);
    const message =
      err instanceof Error ? err.message : "Could not record your vote";
    toast.error(message);
  }, []);

  const [upvote, { loading: upvoting }] = useMutation<
    UpvoteCorpusOutput,
    VoteCorpusInput
  >(UPVOTE_CORPUS, {
    update: (cache, { data }) => updateCorpusVoteCache(cache, data?.voteCorpus),
    onCompleted: (data) => {
      if (!data.voteCorpus.ok) {
        setOptimisticVote(undefined);
        toast.error(data.voteCorpus.message || "Could not upvote");
      } else {
        setOptimisticVote(undefined);
      }
    },
    onError: onMutationError,
  });

  const [downvote, { loading: downvoting }] = useMutation<
    DownvoteCorpusOutput,
    VoteCorpusInput
  >(DOWNVOTE_CORPUS, {
    update: (cache, { data }) => updateCorpusVoteCache(cache, data?.voteCorpus),
    onCompleted: (data) => {
      if (!data.voteCorpus.ok) {
        setOptimisticVote(undefined);
        toast.error(data.voteCorpus.message || "Could not downvote");
      } else {
        setOptimisticVote(undefined);
      }
    },
    onError: onMutationError,
  });

  const [removeVote, { loading: removing }] = useMutation<
    RemoveCorpusVoteOutput,
    RemoveCorpusVoteInput
  >(REMOVE_CORPUS_VOTE, {
    update: (cache, { data }) =>
      updateCorpusVoteCache(cache, data?.removeCorpusVote),
    onCompleted: (data) => {
      if (!data.removeCorpusVote.ok) {
        setOptimisticVote(undefined);
        toast.error(data.removeCorpusVote.message || "Could not remove vote");
      } else {
        setOptimisticVote(undefined);
      }
    },
    onError: onMutationError,
  });

  const busy = upvoting || downvoting || removing;
  const disabled = isOwn || busy;

  // Stop click from bubbling to the parent CardWrapper (otherwise clicking
  // the arrow navigates into the corpus). Each handler also short-circuits
  // when self-voting or already-busy.  Memoized so the Pill wrapper
  // receives a stable ``onClick`` reference between renders (the arrow
  // handlers below are already ``useCallback`` wrapped — keeping ``stop``
  // stable means none of them get a new identity per render).
  const stop = useCallback((event: React.MouseEvent) => {
    // The vote pill is overlaid on the corpus card; stopPropagation
    // alone prevents the card's navigation onClick from firing.
    // preventDefault was a stale carry-over and would suppress form
    // submission if the pill ever lands inside a <form>.
    event.stopPropagation();
  }, []);

  const handleUpvote = useCallback(
    (event: React.MouseEvent) => {
      stop(event);
      if (disabled) {
        if (isOwn) toast.info("You cannot vote on your own corpus");
        return;
      }
      if (effectiveVote === "UPVOTE") {
        setOptimisticVote(null);
        void removeVote({ variables: { corpusId } });
      } else {
        setOptimisticVote("UPVOTE");
        void upvote({ variables: { corpusId } });
      }
    },
    [stop, disabled, isOwn, effectiveVote, corpusId, upvote, removeVote]
  );

  const handleDownvote = useCallback(
    (event: React.MouseEvent) => {
      stop(event);
      if (disabled) {
        if (isOwn) toast.info("You cannot vote on your own corpus");
        return;
      }
      if (effectiveVote === "DOWNVOTE") {
        setOptimisticVote(null);
        void removeVote({ variables: { corpusId } });
      } else {
        setOptimisticVote("DOWNVOTE");
        void downvote({ variables: { corpusId } });
      }
    },
    [stop, disabled, isOwn, effectiveVote, corpusId, downvote, removeVote]
  );

  const title = isOwn
    ? "You cannot vote on your own corpus"
    : "Click to upvote or downvote";

  return (
    <Pill
      data-testid={testId}
      title={title}
      onClick={stop}
      $vertical={isVertical}
    >
      <ArrowButton
        type="button"
        $variant="up"
        $active={effectiveVote === "UPVOTE"}
        $disabled={disabled}
        aria-label="Upvote corpus"
        aria-pressed={effectiveVote === "UPVOTE"}
        onClick={handleUpvote}
      >
        <ChevronUp size={14} />
      </ArrowButton>
      <Score
        $score={displayScore}
        $vertical={isVertical}
        aria-label={`Score: ${displayScore}`}
      >
        {displayScore}
      </Score>
      <ArrowButton
        type="button"
        $variant="down"
        $active={effectiveVote === "DOWNVOTE"}
        $disabled={disabled}
        aria-label="Downvote corpus"
        aria-pressed={effectiveVote === "DOWNVOTE"}
        onClick={handleDownvote}
      >
        <ChevronDown size={14} />
      </ArrowButton>
    </Pill>
  );
});

export default CorpusVoteWidget;
