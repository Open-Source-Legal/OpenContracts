/**
 * Component tests for the per-message "Save to My Documents" control.
 *
 * A chat answer otherwise leaves no artifact, so this control is the only way
 * to keep one. The behaviours worth pinning are: it appears only on finished
 * assistant messages, it sends exactly the variables the server expects, and
 * blank fields mean "derive it" rather than "set it to empty string".
 */
import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
// Split-import rule (CLAUDE.md pitfall #16): mounted components get their own
// import statement, apart from the constant/helper imports below.
import { ChatMessageTestWrapper } from "./ChatMessageTestWrapper";
import { ChatMessage } from "../src/components/widgets/chat/ChatMessage";
import { SAVE_MESSAGE_TO_WORKSPACE } from "../src/graphql/mutations";

const MESSAGE_ID = "TWVzc2FnZVR5cGU6NDI=";

const baseProps = {
  messageId: MESSAGE_ID,
  user: "admin",
  content: "## Key finding\n\nThe July 11 process replaces the legacy one.",
  timestamp: "10:30 AM",
  isAssistant: true,
  isComplete: true,
};

const savedDocument = {
  id: "RG9jdW1lbnRUeXBlOjk5",
  title: "Pinned answer",
  fileType: "text/markdown",
  __typename: "DocumentType",
};

/** Mocks match variables EXACTLY — a drifting mock silently fails to match. */
const buildSaveMock = (
  variables: Record<string, unknown>,
  ok = true
): MockedResponse => ({
  request: { query: SAVE_MESSAGE_TO_WORKSPACE, variables },
  result: {
    data: {
      saveMessageToWorkspace: {
        ok,
        message: ok
          ? "Saved to My Documents as 'Pinned answer'."
          : "Could not save this message to your workspace.",
        obj: ok ? savedDocument : null,
        __typename: "SaveMessageToWorkspaceMutation",
      },
    },
  },
});

test.describe("SaveMessageToWorkspace", () => {
  test("is offered on a finished assistant message", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage {...baseProps} />
      </ChatMessageTestWrapper>
    );

    await expect(
      page.getByTestId("save-message-to-workspace-trigger")
    ).toBeVisible({ timeout: 20000 });
  });

  test("is withheld from user messages and from in-flight answers", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage {...baseProps} isAssistant={false} />
      </ChatMessageTestWrapper>
    );
    await expect(
      page.getByTestId("save-message-to-workspace-trigger")
    ).toHaveCount(0);

    // A half-streamed answer is not worth saving.
    await component.unmount();
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage {...baseProps} isComplete={false} />
      </ChatMessageTestWrapper>
    );
    await expect(
      page.getByTestId("save-message-to-workspace-trigger")
    ).toHaveCount(0);
  });

  test("saves with an explicit title and folder", async ({ mount, page }) => {
    await mount(
      <ChatMessageTestWrapper
        mocks={[
          buildSaveMock({
            messageId: MESSAGE_ID,
            title: "Pinned answer",
            folderName: "Saved Answers",
          }),
        ]}
      >
        <ChatMessage {...baseProps} />
      </ChatMessageTestWrapper>
    );

    await page.getByTestId("save-message-to-workspace-trigger").click();
    await expect(
      page.getByTestId("save-message-to-workspace-popover")
    ).toBeVisible({ timeout: 20000 });

    await page.getByTestId("save-message-title-input").fill("Pinned answer");
    await page.getByTestId("save-message-folder-input").fill("Saved Answers");
    await page.getByTestId("save-message-confirm").click();

    await expect(page.getByText(/Saved to My Documents/)).toBeVisible({
      timeout: 20000,
    });
    // A successful save closes the popover.
    await expect(
      page.getByTestId("save-message-to-workspace-popover")
    ).toHaveCount(0);
  });

  test("blank fields are omitted, not sent as empty strings", async ({
    mount,
    page,
  }) => {
    // Server-side, "" would be an explicit empty title / folder rather than
    // "derive the title" / "save at the workspace root". If the component sent
    // "", this mock would not match and no success toast would appear.
    await mount(
      <ChatMessageTestWrapper
        mocks={[
          buildSaveMock({
            messageId: MESSAGE_ID,
            title: undefined,
            folderName: undefined,
          }),
        ]}
      >
        <ChatMessage {...baseProps} />
      </ChatMessageTestWrapper>
    );

    await page.getByTestId("save-message-to-workspace-trigger").click();
    await page.getByTestId("save-message-folder-input").fill("");
    await page.getByTestId("save-message-confirm").click();

    await expect(page.getByText(/Saved to My Documents/)).toBeVisible({
      timeout: 20000,
    });
  });

  test("surfaces a refusal without closing the popover", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper
        mocks={[
          buildSaveMock(
            {
              messageId: MESSAGE_ID,
              title: undefined,
              folderName: "Saved Answers",
            },
            false
          ),
        ]}
      >
        <ChatMessage {...baseProps} />
      </ChatMessageTestWrapper>
    );

    await page.getByTestId("save-message-to-workspace-trigger").click();
    await page.getByTestId("save-message-confirm").click();

    await expect(page.getByText(/Could not save this message/)).toBeVisible({
      timeout: 20000,
    });
    // The user keeps their typed title/folder to retry.
    await expect(
      page.getByTestId("save-message-to-workspace-popover")
    ).toBeVisible();
  });
});
