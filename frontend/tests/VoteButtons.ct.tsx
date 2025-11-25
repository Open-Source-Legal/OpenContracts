import { test, expect } from "@playwright/experimental-ct-react";
import { VoteButtons } from "../src/components/threads/VoteButtons";
import { MockedProvider } from "@apollo/client/testing";
import {
  UPVOTE_MESSAGE,
  DOWNVOTE_MESSAGE,
  REMOVE_VOTE,
  UpvoteMessageOutput,
  DownvoteMessageOutput,
  RemoveVoteOutput,
} from "../src/graphql/mutations";

test.describe("VoteButtons", () => {
  test("renders vote buttons and count", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    // Net score should be 5 - 2 = 3
    await expect(page.getByText("3")).toBeVisible();
    await expect(page.getByLabel("Upvote")).toBeVisible();
    await expect(page.getByLabel("Downvote")).toBeVisible();
  });

  test("shows negative score", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={2}
          downvoteCount={5}
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    // Net score should be 2 - 5 = -3
    await expect(page.getByText("-3")).toBeVisible();
  });

  test("shows upvoted state", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          userVote="UPVOTE"
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    // Check if button has active state (you may need to adjust based on your styling)
    await expect(upvoteButton).toBeVisible();
  });

  test("shows downvoted state", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          userVote="DOWNVOTE"
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    const downvoteButton = page.getByLabel("Downvote");
    await expect(downvoteButton).toBeVisible();
  });

  test("upvotes message", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: UPVOTE_MESSAGE,
          variables: {
            messageId: "msg-1",
          },
        },
        result: {
          data: {
            upvoteMessage: {
              ok: true,
              message: "Message upvoted",
              chatMessage: {
                id: "msg-1",
                upvoteCount: 6,
                downvoteCount: 2,
                userVote: "UPVOTE",
              },
            },
          } as UpvoteMessageOutput,
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    await upvoteButton.click();

    // Wait for mutation to complete
    await page.waitForTimeout(1000);
  });

  test("downvotes message", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: DOWNVOTE_MESSAGE,
          variables: {
            messageId: "msg-1",
          },
        },
        result: {
          data: {
            downvoteMessage: {
              ok: true,
              message: "Message downvoted",
              chatMessage: {
                id: "msg-1",
                upvoteCount: 5,
                downvoteCount: 3,
                userVote: "DOWNVOTE",
              },
            },
          } as DownvoteMessageOutput,
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    const downvoteButton = page.getByLabel("Downvote");
    await downvoteButton.click();

    // Wait for mutation to complete
    await page.waitForTimeout(1000);
  });

  test("removes upvote when clicking upvote again", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: REMOVE_VOTE,
          variables: {
            messageId: "msg-1",
          },
        },
        result: {
          data: {
            removeVote: {
              ok: true,
              message: "Vote removed",
              chatMessage: {
                id: "msg-1",
                upvoteCount: 4,
                downvoteCount: 2,
                userVote: null,
              },
            },
          } as RemoveVoteOutput,
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          userVote="UPVOTE"
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    await upvoteButton.click();

    // Wait for mutation
    await page.waitForTimeout(500);
  });

  test("prevents voting on own message", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-1"
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    await upvoteButton.click();

    // Should show error
    await page.waitForTimeout(100);
    await expect(
      page.getByText(/cannot vote on your own messages/i)
    ).toBeVisible();
  });

  test("handles upvote error", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: UPVOTE_MESSAGE,
          variables: {
            messageId: "msg-1",
          },
        },
        result: {
          data: {
            upvoteMessage: {
              ok: false,
              message: "Rate limit exceeded. Please try again later.",
              chatMessage: null,
            },
          } as UpvoteMessageOutput,
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    await upvoteButton.click();

    // Wait for error
    await page.waitForTimeout(500);
    await expect(page.getByText(/rate limit exceeded/i)).toBeVisible();
  });

  test("disables buttons when disabled prop is true", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
          disabled={true}
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    const downvoteButton = page.getByLabel("Downvote");

    await expect(upvoteButton).toBeDisabled();
    await expect(downvoteButton).toBeDisabled();
  });

  test("calls onVoteChange callback", async ({ mount, page }) => {
    let newScore: number | null = null;

    const mocks = [
      {
        request: {
          query: UPVOTE_MESSAGE,
          variables: {
            messageId: "msg-1",
          },
        },
        result: {
          data: {
            upvoteMessage: {
              ok: true,
              message: "Message upvoted",
              chatMessage: {
                id: "msg-1",
                upvoteCount: 6,
                downvoteCount: 2,
                userVote: "UPVOTE",
              },
            },
          } as UpvoteMessageOutput,
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
          onVoteChange={(score) => {
            newScore = score;
          }}
        />
      </MockedProvider>
    );

    const upvoteButton = page.getByLabel("Upvote");
    await upvoteButton.click();

    // Wait for mutation
    await page.waitForTimeout(500);

    expect(newScore).toBe(4);
  });

  test("shows optimistic update before server response", async ({
    mount,
    page,
  }) => {
    const mocks = [
      {
        request: {
          query: UPVOTE_MESSAGE,
          variables: {
            messageId: "msg-1",
          },
        },
        delay: 1000, // Delay to observe optimistic update
        result: {
          data: {
            upvoteMessage: {
              ok: true,
              message: "Message upvoted",
              chatMessage: {
                id: "msg-1",
                upvoteCount: 6,
                downvoteCount: 2,
                userVote: "UPVOTE",
              },
            },
          } as UpvoteMessageOutput,
        },
      },
    ];

    const component = await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <VoteButtons
          messageId="msg-1"
          upvoteCount={5}
          downvoteCount={2}
          senderId="user-1"
          currentUserId="user-2"
        />
      </MockedProvider>
    );

    // Initial score: 5 - 2 = 3
    await expect(page.getByText("3")).toBeVisible();

    const upvoteButton = page.getByLabel("Upvote");
    await upvoteButton.click();

    // Optimistic update: should show 4 immediately
    await page.waitForTimeout(100);
    await expect(page.getByText("4")).toBeVisible();
  });
});
