import { describe, it, expect, afterEach, beforeEach } from "vitest";
import { getRuntimeEnv } from "../env";

describe("getRuntimeEnv", () => {
  let originalWindowEnv: unknown;

  beforeEach(() => {
    originalWindowEnv = (window as any)._env_;
  });

  afterEach(() => {
    (window as any)._env_ = originalWindowEnv;
  });

  it("falls back to default values when nothing is injected", () => {
    (window as any)._env_ = {};
    const env = getRuntimeEnv();

    expect(env.REACT_APP_APPLICATION_DOMAIN).toBe("");
    expect(env.REACT_APP_API_ROOT_URL).toBe("http://localhost:8000");
    expect(env.REACT_APP_POSTHOG_HOST).toBe("https://us.i.posthog.com");
    expect(env.REACT_APP_USE_AUTH0).toBe(false);
    expect(env.REACT_APP_USE_ANALYZERS).toBe(false);
    expect(env.REACT_APP_ALLOW_IMPORTS).toBe(false);
  });

  it("reads string values from window._env_", () => {
    (window as any)._env_ = {
      REACT_APP_APPLICATION_DOMAIN: "auth.example.com",
      REACT_APP_API_ROOT_URL: "https://api.example.com",
      REACT_APP_AUDIENCE: "aud",
      REACT_APP_POSTHOG_API_KEY: "phc_key",
    };

    const env = getRuntimeEnv();
    expect(env.REACT_APP_APPLICATION_DOMAIN).toBe("auth.example.com");
    expect(env.REACT_APP_API_ROOT_URL).toBe("https://api.example.com");
    expect(env.REACT_APP_AUDIENCE).toBe("aud");
    expect(env.REACT_APP_POSTHOG_API_KEY).toBe("phc_key");
  });

  it("coerces truthy boolean-like strings", () => {
    (window as any)._env_ = {
      REACT_APP_USE_AUTH0: "true",
      REACT_APP_USE_ANALYZERS: "1",
      REACT_APP_ALLOW_IMPORTS: "YES",
    };

    const env = getRuntimeEnv();
    expect(env.REACT_APP_USE_AUTH0).toBe(true);
    expect(env.REACT_APP_USE_ANALYZERS).toBe(true);
    expect(env.REACT_APP_ALLOW_IMPORTS).toBe(true);
  });

  it("coerces native booleans", () => {
    (window as any)._env_ = {
      REACT_APP_USE_AUTH0: true,
      REACT_APP_USE_ANALYZERS: false,
    };
    const env = getRuntimeEnv();
    expect(env.REACT_APP_USE_AUTH0).toBe(true);
    expect(env.REACT_APP_USE_ANALYZERS).toBe(false);
  });

  it("returns false for falsy boolean-like strings", () => {
    (window as any)._env_ = {
      REACT_APP_USE_AUTH0: "false",
      REACT_APP_USE_ANALYZERS: "0",
      REACT_APP_ALLOW_IMPORTS: "no",
    };

    const env = getRuntimeEnv();
    expect(env.REACT_APP_USE_AUTH0).toBe(false);
    expect(env.REACT_APP_USE_ANALYZERS).toBe(false);
    expect(env.REACT_APP_ALLOW_IMPORTS).toBe(false);
  });

  it("coerces non-string values to strings", () => {
    (window as any)._env_ = {
      REACT_APP_APPLICATION_CLIENT_ID: 12345,
    };
    const env = getRuntimeEnv();
    expect(env.REACT_APP_APPLICATION_CLIENT_ID).toBe("12345");
  });
});
