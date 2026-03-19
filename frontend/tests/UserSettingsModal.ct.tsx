import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedResponse } from "@apollo/client/testing";
import { UPDATE_ME } from "../src/graphql/mutations";
import { GET_USER_BADGES } from "../src/graphql/queries";
import UserSettingsModalHarness from "./UserSettingsModalHarness";
import { docScreenshot } from "./utils/docScreenshot";

const badgesMock: MockedResponse = {
  request: {
    query: GET_USER_BADGES,
    variables: { userId: "user-1", corpusId: undefined, limit: 100 },
  },
  result: {
    data: {
      userBadges: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
      },
    },
  },
};

test("@slug profile modal updates user slug", async ({ mount, page }) => {
  const mocks: ReadonlyArray<MockedResponse> = [
    badgesMock,
    {
      request: {
        query: UPDATE_ME,
        variables: { slug: "Alice-Pro" },
      },
      result: {
        data: {
          updateMe: {
            ok: true,
            message: "Success",
            user: {
              __typename: "UserType",
              id: "user-1",
              username: "alice",
              slug: "Alice-Pro",
            },
          },
        },
      },
    },
  ];

  await mount(<UserSettingsModalHarness mocks={mocks} />);
  await expect(page.getByText("User Settings")).toBeVisible({ timeout: 10000 });

  await docScreenshot(page, "settings--user-settings-modal--initial");

  const slugInput = page.getByPlaceholder("your-slug");
  await slugInput.fill("Alice-Pro");

  // Verify the input value was set
  await expect(slugInput).toHaveValue("Alice-Pro");

  // Save the changes
  const saveButton = page.getByRole("button", { name: /Save/i });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();

  // Wait a bit to let any mutations process
  await page.waitForTimeout(500);
});
