import { describe, it, expect, afterEach, beforeEach } from "vitest";

import defaultContent from "../default.json";
import publicRecordContent from "../publicRecord.json";
import { useLandingContent } from "../index";
import { cleanup, renderHook } from "../../../test-utils/renderHook";

/**
 * Hook-level coverage for `useLandingContent`. The bundled-variant
 * registry is exercised in `landingContent.test.ts`; here we confirm
 * that the hook actually resolves the active variant from the runtime
 * env and falls back to "default" when REACT_APP_LANDING_VARIANT is
 * absent or unknown.
 *
 * `useLandingContent` reads through `useEnv` -> `getRuntimeEnv` which
 * pulls from `window._env_` at runtime, so each test simply swaps that
 * injection in/out around the hook render. No module mock needed.
 */
describe("useLandingContent", () => {
  let originalWindowEnv: unknown;

  beforeEach(() => {
    originalWindowEnv = (window as any)._env_;
  });

  afterEach(() => {
    cleanup();
    (window as any)._env_ = originalWindowEnv;
  });

  it("returns the default variant when REACT_APP_LANDING_VARIANT is unset", () => {
    (window as any)._env_ = {};
    const { result } = renderHook(() => useLandingContent());
    expect(result.current).toBe(defaultContent);
  });

  it("returns the public-record variant when env selects it", () => {
    (window as any)._env_ = { REACT_APP_LANDING_VARIANT: "public-record" };
    const { result } = renderHook(() => useLandingContent());
    expect(result.current).toBe(publicRecordContent);
  });

  it("switching variants yields divergent headline + About copy", () => {
    // Render the default first.
    (window as any)._env_ = { REACT_APP_LANDING_VARIANT: "default" };
    const { result: defaultHook } = renderHook(() => useLandingContent());
    const defaultHero = defaultHook.current.hero;
    const defaultAbout = defaultHook.current.about;

    // Then render the public-record variant in a fresh hook scope.
    (window as any)._env_ = { REACT_APP_LANDING_VARIANT: "public-record" };
    const { result: publicRecordHook } = renderHook(() => useLandingContent());
    const publicRecordHero = publicRecordHook.current.hero;
    const publicRecordAbout = publicRecordHook.current.about;

    // hero.accent + hero.subheadline are the variant's principal copy
    // levers on the landing surface; about.title is the principal lever
    // on the /about route. All must diverge or the two variants are
    // functionally collapsed.
    expect(publicRecordHero.accent).not.toBe(defaultHero.accent);
    expect(publicRecordHero.subheadline).not.toBe(defaultHero.subheadline);
    expect(publicRecordAbout.title).not.toBe(defaultAbout.title);
  });

  it("falls back to the default variant when given an unknown key", () => {
    (window as any)._env_ = {
      REACT_APP_LANDING_VARIANT: "this-variant-does-not-exist",
    };
    const { result } = renderHook(() => useLandingContent());
    // Same object identity, not just deep-equal — the registry lookup
    // hands the default reference through unchanged when the key misses.
    expect(result.current).toBe(defaultContent);
  });
});
