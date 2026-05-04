/**
 * React-18-native renderHook helper.
 *
 * The legacy `@testing-library/react-hooks` package still calls the
 * `ReactDOM.render` API, which prints a "ReactDOM.render is no longer
 * supported in React 18" warning on every test that uses it. This helper
 * mirrors the small slice of that API we actually need (renderHook +
 * unmount + rerender + result.current) on top of `react-dom/client`'s
 * `createRoot`, so new and migrated tests can run quietly in React 18.
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

export interface RenderHookResult<TProps, TResult> {
  result: { current: TResult };
  rerender: (props?: TProps) => void;
  unmount: () => void;
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
  initialProps?: TProps
): RenderHookResult<TProps, TResult> {
  const result = { current: undefined as unknown as TResult };
  const container = document.createElement("div");
  document.body.appendChild(container);
  let root: Root | null = null;

  const HookProbe: React.FC<{ hookProps: TProps }> = ({ hookProps }) => {
    result.current = callback(hookProps);
    return null;
  };

  act(() => {
    root = createRoot(container);
    root.render(<HookProbe hookProps={initialProps as TProps} />);
  });

  const entry: LiveRoot = { root: root as unknown as Root, container };
  liveRoots.add(entry);

  return {
    result,
    rerender: (props?: TProps) => {
      act(() => {
        root?.render(
          <HookProbe hookProps={(props ?? initialProps) as TProps} />
        );
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
  };
}

export { act };
