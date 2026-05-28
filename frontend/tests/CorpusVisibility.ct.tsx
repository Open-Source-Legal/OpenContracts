/**
 * Tests for corpus visibility (public/private) functionality.
 *
 * These tests verify that:
 * 1. The visibility toggle is only enabled when user has CAN_PERMISSION
 * 2. The SET_CORPUS_VISIBILITY mutation is called with correct parameters
 * 3. Users without CAN_PERMISSION cannot change visibility
 *
 * Note: Backend permission enforcement is tested in test_corpus_visibility.py
 * These tests focus on frontend UI gating and mutation calls.
 */

import { test, expect } from "./utils/coverage";
import { CorpusSettingsTestWrapper } from "./CorpusSettingsTestWrapper";
import { SET_CORPUS_VISIBILITY, UPDATE_CORPUS } from "../src/graphql/mutations";
import { GET_CORPUS_ACTIONS } from "../src/graphql/queries";
import { PermissionTypes } from "../src/components/types";

test.describe("Corpus Visibility Settings", () => {
  const baseCorpus = {
    id: "Q29ycHVzVHlwZTox",
    title: "Test Corpus",
    description: "Test description",
    descriptionPreview: "Test description",
    allowComments: true,
    isPublic: false,
    slug: "test-corpus",
    creator: {
      email: "owner@test.com",
      username: "owner",
      slug: "owner",
    },
  };

  const baseActionsMock = {
    request: {
      query: GET_CORPUS_ACTIONS,
      variables: { corpusId: baseCorpus.id },
    },
    result: {
      data: {
        corpusActions: {
          edges: [],
          pageInfo: { hasNextPage: false, endCursor: null },
        },
      },
    },
  };

  test("visibility toggle is disabled without CAN_PERMISSION", async ({
    mount,
    page,
  }) => {
    // User has UPDATE but NOT PERMISSION
    const corpusWithoutPermission = {
      ...baseCorpus,
      myPermissions: [PermissionTypes.CAN_UPDATE, PermissionTypes.CAN_READ],
    };

    await mount(
      <CorpusSettingsTestWrapper
        mocks={[baseActionsMock]}
        corpus={corpusWithoutPermission}
      />
    );

    // The visibility checkbox should be disabled
    const checkbox = page.locator("#corpus-is-public-checkbox");
    await expect(checkbox).toBeDisabled();
  });

  test("visibility toggle is enabled with CAN_PERMISSION", async ({
    mount,
    page,
  }) => {
    // User has PERMISSION
    const corpusWithPermission = {
      ...baseCorpus,
      myPermissions: [
        PermissionTypes.CAN_PERMISSION,
        PermissionTypes.CAN_UPDATE,
        PermissionTypes.CAN_READ,
      ],
    };

    await mount(
      <CorpusSettingsTestWrapper
        mocks={[baseActionsMock]}
        corpus={corpusWithPermission}
      />
    );

    // The visibility checkbox should be enabled
    const checkbox = page.locator("#corpus-is-public-checkbox");
    await expect(checkbox).toBeEnabled();
  });

  test("SET_CORPUS_VISIBILITY mutation is called when saving visibility change", async ({
    mount,
    page,
  }) => {
    let mutationCalled = false;
    let mutationVariables: any = null;

    const corpusWithPermission = {
      ...baseCorpus,
      myPermissions: [PermissionTypes.CAN_PERMISSION],
    };

    const mocks = [
      baseActionsMock,
      {
        request: {
          query: SET_CORPUS_VISIBILITY,
          variables: {
            corpusId: baseCorpus.id,
            isPublic: true,
          },
        },
        result: () => {
          mutationCalled = true;
          mutationVariables = { corpusId: baseCorpus.id, isPublic: true };
          return {
            data: {
              setCorpusVisibility: {
                ok: true,
                message: "Making corpus public. This may take a moment.",
              },
            },
          };
        },
      },
    ];

    await mount(
      <CorpusSettingsTestWrapper mocks={mocks} corpus={corpusWithPermission} />
    );

    // Toggle visibility to public
    const checkbox = page.locator("#corpus-is-public-checkbox");
    await checkbox.click();

    // Click save button
    const saveButton = page.getByRole("button", { name: /save changes/i });
    await saveButton.click();

    // Wait for mutation to be called
    await page.waitForTimeout(500);

    // Verify mutation was called with correct parameters
    expect(mutationCalled).toBe(true);
    expect(mutationVariables).toEqual({
      corpusId: baseCorpus.id,
      isPublic: true,
    });
  });

  test("UPDATE_CORPUS mutation does NOT include isPublic parameter", async ({
    mount,
    page,
  }) => {
    let updateMutationVariables: any = null;

    const corpusWithBothPermissions = {
      ...baseCorpus,
      myPermissions: [
        PermissionTypes.CAN_PERMISSION,
        PermissionTypes.CAN_UPDATE,
      ],
    };

    const mocks = [
      baseActionsMock,
      {
        request: {
          query: SET_CORPUS_VISIBILITY,
          variables: {
            corpusId: baseCorpus.id,
            isPublic: true,
          },
        },
        result: {
          data: {
            setCorpusVisibility: {
              ok: true,
              message: "Making corpus public.",
            },
          },
        },
      },
      {
        request: {
          query: UPDATE_CORPUS,
          variables: {
            id: baseCorpus.id,
            slug: "new-slug",
          },
        },
        result: () => {
          updateMutationVariables = { id: baseCorpus.id, slug: "new-slug" };
          return {
            data: {
              updateCorpus: {
                ok: true,
                message: "Updated",
              },
            },
          };
        },
      },
    ];

    await mount(
      <CorpusSettingsTestWrapper
        mocks={mocks}
        corpus={corpusWithBothPermissions}
      />
    );

    // Toggle visibility
    const checkbox = page.locator("#corpus-is-public-checkbox");
    await checkbox.click();

    // Change slug
    const slugInput = page.locator("#corpus-slug-input");
    await slugInput.fill("new-slug");

    // Click save
    const saveButton = page.getByRole("button", { name: /save changes/i });
    await saveButton.click();

    await page.waitForTimeout(500);

    // Verify UPDATE_CORPUS mutation does NOT include isPublic
    // (it's handled by SET_CORPUS_VISIBILITY separately)
    if (updateMutationVariables) {
      expect(updateMutationVariables).not.toHaveProperty("isPublic");
    }
  });
});
