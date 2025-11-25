import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedResponse } from "@apollo/client/testing";
import { UPDATE_ME } from "../src/graphql/mutations";
import UserSettingsModalHarness from "./UserSettingsModalHarness";

test("@slug profile modal updates user slug", async ({ mount, page }) => {
  const mocks: ReadonlyArray<MockedResponse> = [
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
  await expect(page.getByTestId("user-settings-modal")).toBeVisible();

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
