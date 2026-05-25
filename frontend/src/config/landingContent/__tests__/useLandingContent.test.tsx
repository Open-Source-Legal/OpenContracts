import { describe, it, expect, vi, beforeEach } from "vitest";

import defaultContent from "../default.json";
import publicRecordContent from "../publicRecord.json";
import { useLandingContent } from "../index";
import { useEnv } from "../../../components/hooks/UseEnv";
import { cleanup, renderHook } from "../../../test-utils/renderHook";

/**
 * Hook-level coverage for `useLandingContent`. The bundled-variant
 * registry is exercised in `landingContent.test.ts`; here we confirm
 * that the hook actually resolves the active variant from the runtime
 * env and falls back to "default" when REACT_APP_LANDING_VARIANT is
 * absent or unknown.
 *
 * `useLandingContent` reads through `useEnv()` -> `getRuntimeEnv()`,
 * so we stub `useEnv` directly rather than fiddling with `window._env_`
 * (whose ambient type would require a wide compatibility shim here).
 */
vi.mock("../../../components/hooks/UseEnv", () => ({
  useEnv: vi.fn(),
}));

// Minimal EnvConfig stub. Every key in src/utils/env.ts must be present so
// the return value satisfies the typed `EnvConfig` shape; only the
// REACT_APP_LANDING_VARIANT field actually matters to this hook.
const envWith = (variant: string) =>
  ({
    REACT_APP_APPLICATION_DOMAIN: "",
    REACT_APP_APPLICATION_CLIENT_ID: "",
    REACT_APP_AUDIENCE: "",
    REACT_APP_API_ROOT_URL: "http://localhost:8000",
    REACT_APP_USE_AUTH0: false,
    REACT_APP_USE_ANALYZERS: false,
    REACT_APP_ALLOW_IMPORTS: false,
    REACT_APP_POSTHOG_API_KEY: "",
    REACT_APP_POSTHOG_HOST: "https://us.i.posthog.com",
    REACT_APP_LANDING_VARIANT: variant,
  } as const);

describe("useLandingContent", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(useEnv).mockReset();
  });

  it("returns the default variant when REACT_APP_LANDING_VARIANT is unset", () => {
    vi.mocked(useEnv).mockReturnValue(envWith(""));
    const { result } = renderHook(() => useLandingContent());
    expect(result.current).toBe(defaultContent);
  });

  it("returns the public-record variant when env selects it", () => {
    vi.mocked(useEnv).mockReturnValue(envWith("public-record"));
    const { result } = renderHook(() => useLandingContent());
    expect(result.current).toBe(publicRecordContent);
  });

  it("switching variants yields divergent headline + About copy", () => {
    // Render the default first.
    vi.mocked(useEnv).mockReturnValue(envWith("default"));
    const { result: defaultHook } = renderHook(() => useLandingContent());
    const defaultHero = defaultHook.current.hero;
    const defaultAbout = defaultHook.current.about;

    // Then render the public-record variant in a fresh hook scope.
    vi.mocked(useEnv).mockReturnValue(envWith("public-record"));
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
    vi.mocked(useEnv).mockReturnValue(envWith("this-variant-does-not-exist"));
    const { result } = renderHook(() => useLandingContent());
    // Same object identity, not just deep-equal — the registry lookup
    // hands the default reference through unchanged when the key misses.
    expect(result.current).toBe(defaultContent);
  });
});
