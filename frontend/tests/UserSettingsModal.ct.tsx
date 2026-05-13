import React from "react";
import { test, expect } from "./utils/coverage";
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

test("markdown profile fields are editable and surface a focus ring", async ({
  mount,
  page,
}) => {
  // Pin the new markdown fields added in this PR: the headline Input plus
  // the about/links MarkdownTextareas must be present, accept input, and
  // expose a visible focus indicator (WCAG 2.4.7) — the previous
  // implementation relied on border-color alone, which is invisible in
  // forced-colors mode. We assert the focus shadow is non-empty rather
  // than pinning an exact rgba string so future colour token tweaks
  // don't churn the test.
  await mount(<UserSettingsModalHarness mocks={[badgesMock]} />);
  await expect(page.getByText("User Settings")).toBeVisible({ timeout: 10000 });

  const headline = page.getByPlaceholder(
    "What do you do? (e.g. Contracts counsel + legal ops)"
  );
  await expect(headline).toBeVisible();
  await headline.fill("Senior contracts engineer");
  await expect(headline).toHaveValue("Senior contracts engineer");

  const about = page.locator("#profile-about-markdown");
  await expect(about).toBeVisible();
  await about.fill("I'm **interested** in dispute resolution.");
  await expect(about).toHaveValue("I'm **interested** in dispute resolution.");

  const links = page.locator("#profile-links-markdown");
  await expect(links).toBeVisible();
  await links.fill("- [home](https://example.com)");
  await expect(links).toHaveValue("- [home](https://example.com)");

  // Focus the about textarea and assert the focus ring kicks in via
  // box-shadow (the WCAG 2.4.7 hardening). A bare `none` shadow means
  // the focus indicator regressed to border-color only.
  await about.focus();
  const aboutShadow = await about.evaluate(
    (el) => window.getComputedStyle(el).boxShadow
  );
  expect(aboutShadow).not.toBe("none");
  expect(aboutShadow.length).toBeGreaterThan(0);

  await docScreenshot(page, "settings--user-settings-modal--markdown-fields");
});
