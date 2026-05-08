/**
 * React-18-native renderHook helper.
 *
 * Replaces `@testing-library/react-hooks` (which still calls the legacy
 * `ReactDOM.render` API and prints a "ReactDOM.render is no longer
 * supported in React 18" warning on every test that uses it). This helper
 * mirrors the slice of that API we actually use — `renderHook` with
 * `wrapper`/`initialProps`, plus `result`, `rerender`, `unmount`,
 * `waitForNextUpdate`, and `waitFor` on the return — on top of
 * `react-dom/client`'s `createRoot`, so all hook tests run quietly in
 * React 18.
 *
 * Cleanup contract: tests must unmount or call `cleanup()` *before* any
 * teardown that fires subscriptions held by the hook (e.g. resetting an
 * Apollo reactive variable that the hook reads via `useReactiveVar`).
 * Otherwise, those subscriptions will trigger state updates against an
 * unwrapped tree and emit "update was not wrapped in act(...)" warnings.
 *
 * Use the `act` re-export from this module rather than from
 * `react-dom/test-utils`; both forward to the same React internal but
 * importing through one path keeps tests consistent.
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

export interface RenderHookOptions<TProps> {
  initialProps?: TProps;
  wrapper?: React.ComponentType<{ children: React.ReactNode }>;
}

export interface WaitOptions {
  timeout?: number;
  interval?: number;
}

export interface RenderHookResult<TProps, TResult> {
  result: { current: TResult };
  rerender: (props?: TProps) => void;
  unmount: () => void;
  waitForNextUpdate: (options?: { timeout?: number }) => Promise<void>;
  waitFor: (callback: () => unknown, options?: WaitOptions) => Promise<void>;
}

interface LiveRoot {
  root: Root;
  container: HTMLElement;
}

const liveRoots = new Set<LiveRoot>();

/**
 * Unmount every root spawned by `renderHook` since the last cleanup.
 * Tests should call this *before* tearing down any external state the
 * hooks subscribe to (e.g. before `authToken("")`).
 */
export function cleanup(): void {
  for (const entry of liveRoots) {
    try {
      act(() => {
        entry.root.unmount();
      });
    } catch {
      // already torn down
    }
    entry.container.remove();
  }
  liveRoots.clear();
}

export function renderHook<TProps, TResult>(
  callback: (props: TProps) => TResult,
  options?: RenderHookOptions<TProps>
): RenderHookResult<TProps, TResult> {
  const { initialProps, wrapper: Wrapper } = options ?? {};
  const result = { current: undefined as unknown as TResult };
  const container = document.createElement("div");
  document.body.appendChild(container);
  let root: Root | null = null;
  let renderCount = 0;

  const HookProbe: React.FC<{ hookProps: TProps }> = ({ hookProps }) => {
    result.current = callback(hookProps);
    renderCount++;
    return null;
  };

  const buildTree = (props: TProps): React.ReactElement => {
    const probe = <HookProbe hookProps={props} />;
    return Wrapper ? <Wrapper>{probe}</Wrapper> : probe;
  };

  act(() => {
    root = createRoot(container);
    root.render(buildTree(initialProps as TProps));
  });

  const entry: LiveRoot = { root: root as unknown as Root, container };
  liveRoots.add(entry);

  return {
    result,
    rerender: (props?: TProps) => {
      act(() => {
        root?.render(buildTree((props ?? initialProps) as TProps));
      });
    },
    unmount: () => {
      act(() => {
        root?.unmount();
        root = null;
      });
      liveRoots.delete(entry);
      container.remove();
    },
    waitForNextUpdate: async ({ timeout = 1000 } = {}) => {
      const startCount = renderCount;
      const start = Date.now();
      // Each iteration wraps its sleep in a fresh `act` so React flushes any
      // pending state updates (Apollo cache writes, fetch resolutions,
      // reactive-var subscribers, etc.) between polls. A single act boundary
      // wrapping the whole loop would defer the flush until the loop exits,
      // so renderCount would never advance.
      while (renderCount <= startCount) {
        if (Date.now() - start >= timeout) {
          throw new Error("Hook did not update before timeout");
        }
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 10));
        });
      }
    },
    waitFor: (callback, options) => waitFor(callback, options),
  };
}

/**
 * Poll a callback until it succeeds, wrapping each iteration in `act` so
 * React 18 flushes any pending state updates (Apollo resolutions, fetch
 * `.then` setStates, reactive-var subscribers) between polls. Matches the
 * `@testing-library/react-hooks` v8 contract — both `() => expect(...)`
 * (success when the assertion stops throwing) and `() => predicate` (success
 * when the predicate returns truthy) are supported.
 *
 * Exported standalone so tests that previously used `waitFor` from
 * `@testing-library/react` can swap the import without rewriting their
 * assertions; that library's `waitFor` does NOT wrap in act, so under the
 * `IS_REACT_ACT_ENVIRONMENT = true` flag set in `setupTests.ts` async
 * updates from hooks-under-test never surface to the probe and the
 * predicate would never see the post-resolve state.
 */
export async function waitFor(
  callback: () => unknown,
  { timeout = 1000, interval = 50 }: WaitOptions = {}
): Promise<void> {
  const start = Date.now();
  let lastError: unknown = null;
  const tryCallback = (): "success" | "retry" => {
    try {
      const value = callback();
      // Match legacy semantics: a callback that returns nothing (e.g.
      // `() => expect(...)`) is treated as success when it does not throw,
      // a callback that returns truthy is success, and only a thrown error
      // or an explicit falsy return triggers a retry.
      if (value === undefined || value) {
        lastError = null;
        return "success";
      }
    } catch (err) {
      lastError = err;
    }
    return "retry";
  };
  if (tryCallback() === "success") return;
  while (Date.now() - start < timeout) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, interval));
    });
    if (tryCallback() === "success") return;
  }
  throw lastError ?? new Error("waitFor timed out");
}

export { act };
