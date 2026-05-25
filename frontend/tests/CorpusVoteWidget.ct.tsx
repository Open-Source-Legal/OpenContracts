import React from "react";
import { test, expect } from "./utils/coverage";
import { CorpusVoteWidgetTestWrapper } from "./CorpusVoteWidgetTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("CorpusVoteWidget", () => {
  test("renders score and both arrows in the neutral state", async ({
    mount,
  }) => {
    const component = await mount(
      <CorpusVoteWidgetTestWrapper initialScore={5} />
    );

    await expect(component.getByTestId("vote-widget")).toBeVisible();
    await expect(component.getByLabel("Score: 5")).toBeVisible();
    await expect(component.getByLabel("Upvote corpus")).toBeVisible();
    await expect(component.getByLabel("Downvote corpus")).toBeVisible();
  });

  test("upvote optimistically increments the score", async ({ mount }) => {
    const component = await mount(
      <CorpusVoteWidgetTestWrapper initialScore={3} initialMyVote={null} />
    );

    await expect(component.getByLabel("Score: 3")).toBeVisible();
    await component.getByLabel("Upvote corpus").click();
    // Optimistic update bumps the score before the mutation resolves.
    await expect(component.getByLabel("Score: 4")).toBeVisible();
  });

  test("clicking the active arrow removes the vote", async ({ mount }) => {
    const component = await mount(
      <CorpusVoteWidgetTestWrapper initialScore={2} initialMyVote="UPVOTE" />
    );

    await expect(component.getByLabel("Score: 2")).toBeVisible();
    // Already upvoted — clicking it again should fire ``removeVote`` and
    // optimistically decrement.
    await component.getByLabel("Upvote corpus").click();
    await expect(component.getByLabel("Score: 1")).toBeVisible();
  });

  test("self-vote is blocked when viewer owns the corpus", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusVoteWidgetTestWrapper
        initialScore={4}
        creatorId="viewer-1"
        viewerId="viewer-1"
      />
    );

    // Pill renders, but both arrows are disabled and clicks are absorbed.
    const upvote = component.getByLabel("Upvote corpus");
    await expect(upvote).toBeVisible();
    await expect(upvote).toHaveAttribute("aria-pressed", "false");
    await upvote.click();
    // Score does NOT change because the click short-circuits.
    await expect(component.getByLabel("Score: 4")).toBeVisible();
    await docScreenshot(page, "corpus--vote-widget--self-vote-blocked");
  });

  test("downvote optimistically decrements the score", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusVoteWidgetTestWrapper initialScore={1} initialMyVote={null} />
    );

    await expect(component.getByLabel("Score: 1")).toBeVisible();
    await component.getByLabel("Downvote corpus").click();
    await expect(component.getByLabel("Score: 0")).toBeVisible();
    await docScreenshot(page, "corpus--vote-widget--after-downvote");
  });
});
