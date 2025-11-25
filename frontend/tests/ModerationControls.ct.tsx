import { test, expect } from "@playwright/experimental-ct-react";
import { ModerationControls } from "../src/components/threads/ModerationControls";
import { MockedProvider } from "@apollo/client/testing";
import {
  PIN_THREAD,
  UNPIN_THREAD,
  LOCK_THREAD,
  UNLOCK_THREAD,
  DELETE_THREAD,
  RESTORE_THREAD,
  PinThreadOutput,
  UnpinThreadOutput,
  LockThreadOutput,
  UnlockThreadOutput,
  DeleteThreadOutput,
  RestoreThreadOutput,
} from "../src/graphql/mutations";
import { GET_THREAD_DETAIL } from "../src/graphql/queries";

test.describe("ModerationControls", () => {
  test("renders all moderation buttons", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    await expect(page.getByLabel("Pin thread")).toBeVisible();
    await expect(page.getByLabel("Lock thread")).toBeVisible();
    await expect(page.getByLabel("Delete thread")).toBeVisible();
  });

  test("shows unpin when thread is pinned", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={true}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    await expect(page.getByLabel("Unpin thread")).toBeVisible();
    await expect(page.getByText("Unpin")).toBeVisible();
  });

  test("shows unlock when thread is locked", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={true}
          isDeleted={false}
        />
      </MockedProvider>
    );

    await expect(page.getByLabel("Unlock thread")).toBeVisible();
    await expect(page.getByText("Unlock")).toBeVisible();
  });

  test("shows restore button when thread is deleted", async ({
    mount,
    page,
  }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={true}
        />
      </MockedProvider>
    );

    await expect(page.getByLabel("Restore thread")).toBeVisible();
    await expect(page.getByText("Restore")).toBeVisible();
    // Delete button should not be visible
    await expect(page.getByLabel("Delete thread")).not.toBeVisible();
  });

  test("pins thread successfully", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: PIN_THREAD,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            pinThread: {
              ok: true,
              message: "Thread pinned",
              conversation: {
                id: "thread-1",
                isPinned: true,
                pinnedBy: {
                  id: "user-1",
                  username: "moderator",
                },
                pinnedAt: "2025-01-01T00:00:00Z",
              },
            },
          } as PinThreadOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "thread-1",
              isPinned: true,
            },
          },
        },
      },
    ];

    let successCalled = false;

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
          onSuccess={() => {
            successCalled = true;
          }}
        />
      </MockedProvider>
    );

    const pinButton = page.getByLabel("Pin thread");
    await pinButton.click();

    await page.waitForTimeout(500);
    expect(successCalled).toBe(true);
  });

  test("unpins thread successfully", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: UNPIN_THREAD,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            unpinThread: {
              ok: true,
              message: "Thread unpinned",
              conversation: {
                id: "thread-1",
                isPinned: false,
                pinnedBy: null,
                pinnedAt: null,
              },
            },
          } as UnpinThreadOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "thread-1",
              isPinned: false,
            },
          },
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={true}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    const unpinButton = page.getByLabel("Unpin thread");
    await unpinButton.click();

    await page.waitForTimeout(500);
  });

  test("locks thread successfully", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: LOCK_THREAD,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            lockThread: {
              ok: true,
              message: "Thread locked",
              conversation: {
                id: "thread-1",
                isLocked: true,
                lockedBy: {
                  id: "user-1",
                  username: "moderator",
                },
                lockedAt: "2025-01-01T00:00:00Z",
              },
            },
          } as LockThreadOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "thread-1",
              isLocked: true,
            },
          },
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    const lockButton = page.getByLabel("Lock thread");
    await lockButton.click();

    await page.waitForTimeout(500);
  });

  test("shows delete confirmation dialog", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    const deleteButton = page.getByLabel("Delete thread");
    await deleteButton.click();

    // Confirmation dialog should appear
    await expect(page.getByText("Delete Thread?")).toBeVisible();
    await expect(
      page.getByText(/Are you sure you want to delete this thread/)
    ).toBeVisible();
  });

  test("can cancel delete confirmation", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    const deleteButton = page.getByLabel("Delete thread");
    await deleteButton.click();

    // Dialog appears
    await expect(page.getByText("Delete Thread?")).toBeVisible();

    // Click cancel
    const cancelButton = page.getByRole("button", { name: "Cancel" });
    await cancelButton.click();

    // Dialog should disappear
    await page.waitForTimeout(100);
    await expect(page.getByText("Delete Thread?")).not.toBeVisible();
  });

  test("deletes thread after confirmation", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: DELETE_THREAD,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            deleteThread: {
              ok: true,
              message: "Thread deleted",
              conversation: {
                id: "thread-1",
                isDeleted: true,
                deletedBy: {
                  id: "user-1",
                  username: "moderator",
                },
                deletedAt: "2025-01-01T00:00:00Z",
              },
            },
          } as DeleteThreadOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "thread-1",
              isDeleted: true,
            },
          },
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    const deleteButton = page.getByLabel("Delete thread");
    await deleteButton.click();

    // Wait for dialog to appear
    await expect(page.getByText("Delete Thread?")).toBeVisible();

    // Confirm deletion - use exact match on the confirm button in dialog
    const confirmButton = page
      .getByRole("button", {
        name: "Delete Thread",
        exact: true,
      })
      .last();
    await confirmButton.click();

    await page.waitForTimeout(500);

    // Dialog should close
    await expect(page.getByText("Delete Thread?")).not.toBeVisible();
  });

  test("restores deleted thread", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: RESTORE_THREAD,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            restoreThread: {
              ok: true,
              message: "Thread restored",
              conversation: {
                id: "thread-1",
                isDeleted: false,
                deletedBy: null,
                deletedAt: null,
              },
            },
          } as RestoreThreadOutput,
        },
      },
      {
        request: {
          query: GET_THREAD_DETAIL,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            conversation: {
              id: "thread-1",
              isDeleted: false,
            },
          },
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={true}
        />
      </MockedProvider>
    );

    const restoreButton = page.getByLabel("Restore thread");
    await restoreButton.click();

    await page.waitForTimeout(500);
  });

  test("shows error on pin failure", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: PIN_THREAD,
          variables: {
            conversationId: "thread-1",
          },
        },
        result: {
          data: {
            pinThread: {
              ok: false,
              message: "You don't have permission to pin threads",
              conversation: null,
            },
          } as PinThreadOutput,
        },
      },
    ];

    await mount(
      <MockedProvider mocks={mocks} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={false}
        />
      </MockedProvider>
    );

    const pinButton = page.getByLabel("Pin thread");
    await pinButton.click();

    await page.waitForTimeout(500);

    await expect(page.getByText(/don't have permission/i)).toBeVisible();
  });

  test("disables buttons when deleted", async ({ mount, page }) => {
    await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ModerationControls
          conversationId="thread-1"
          isPinned={false}
          isLocked={false}
          isDeleted={true}
        />
      </MockedProvider>
    );

    const pinButton = page.getByLabel("Pin thread");
    const lockButton = page.getByLabel("Lock thread");

    await expect(pinButton).toBeDisabled();
    await expect(lockButton).toBeDisabled();
  });
});
