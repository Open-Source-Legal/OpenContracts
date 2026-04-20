import { describe, it, expect } from "vitest";
import React from "react";
import { renderHook } from "@testing-library/react-hooks";
import { MockedProvider } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { useMessageBadges } from "../useMessageBadges";
import { GET_USER_BADGES } from "../../graphql/queries";

function createWrapper(mocks: any[]) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <MockedProvider
        mocks={mocks}
        addTypename={false}
        cache={new InMemoryCache({ addTypename: false })}
      >
        <>{children}</>
      </MockedProvider>
    );
  };
}

describe("useMessageBadges", () => {
  it("skips the query and returns an empty map when no userIds", () => {
    const { result } = renderHook(() => useMessageBadges([]), {
      wrapper: createWrapper([]),
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.badgesByUser.size).toBe(0);
  });

  it("returns loading=true while the query is in flight", () => {
    const mocks = [
      {
        request: {
          query: GET_USER_BADGES,
          variables: { corpusId: undefined, limit: 5 },
        },
        result: { data: { userBadges: { edges: [] } } },
        delay: 100,
      },
    ];

    const { result } = renderHook(() => useMessageBadges(["u1"]), {
      wrapper: createWrapper(mocks),
    });

    expect(result.current.loading).toBe(true);
    expect(result.current.badgesByUser.size).toBe(0);
  });

  it("groups badges by user id once data resolves", async () => {
    const mocks = [
      {
        request: {
          query: GET_USER_BADGES,
          variables: { corpusId: "corpus-1", limit: 10 },
        },
        result: {
          data: {
            userBadges: {
              edges: [
                {
                  node: {
                    id: "b1",
                    user: { id: "u1", username: "alice" },
                  },
                },
                {
                  node: {
                    id: "b2",
                    user: { id: "u1", username: "alice" },
                  },
                },
                {
                  node: {
                    id: "b3",
                    user: { id: "u2", username: "bob" },
                  },
                },
                // Not in our userIds - should be filtered out.
                {
                  node: {
                    id: "b4",
                    user: { id: "u99", username: "ignored" },
                  },
                },
                null,
              ],
            },
          },
        },
      },
    ];

    const { result, waitFor } = renderHook(
      () => useMessageBadges(["u1", "u2"], "corpus-1", 5),
      { wrapper: createWrapper(mocks) }
    );

    await waitFor(() => !result.current.loading);

    expect(result.current.badgesByUser.get("u1")?.length).toBe(2);
    expect(result.current.badgesByUser.get("u2")?.length).toBe(1);
    expect(result.current.badgesByUser.has("u99")).toBe(false);
  });

  it("caps the number of badges returned per user", async () => {
    const edges = Array.from({ length: 7 }, (_, i) => ({
      node: { id: `b${i}`, user: { id: "u1", username: "alice" } },
    }));

    const mocks = [
      {
        request: {
          query: GET_USER_BADGES,
          variables: { corpusId: undefined, limit: 3 },
        },
        result: { data: { userBadges: { edges } } },
      },
    ];

    const { result, waitFor } = renderHook(
      () => useMessageBadges(["u1"], null, 3),
      { wrapper: createWrapper(mocks) }
    );

    await waitFor(() => !result.current.loading);
    expect(result.current.badgesByUser.get("u1")?.length).toBe(3);
  });
});
