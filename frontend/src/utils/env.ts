/**
 * Centralized runtime environment accessor.
 *
 * Reads configuration from window._env_ if present (runtime-injected),
 * falling back to import.meta.env (build-time) and sensible defaults.
 */

export interface EnvConfig {
  REACT_APP_APPLICATION_DOMAIN: string;
  REACT_APP_APPLICATION_CLIENT_ID: string;
  REACT_APP_AUDIENCE: string;
  REACT_APP_API_ROOT_URL: string;
  REACT_APP_USE_AUTH0: boolean;
  REACT_APP_USE_ANALYZERS: boolean;
  REACT_APP_ALLOW_IMPORTS: boolean;
  REACT_APP_POSTHOG_API_KEY: string;
  REACT_APP_POSTHOG_HOST: string;
  /**
   * Selects the landing/about copy variant. "default" (or unset) ships the
   * world-facing "citation layer for agentic workflows" framing — appropriate
   * for the OSS project's repo and most deployments. Set to "public-record"
   * to ship the public-domain citation-graph framing (the JSv4 deployment).
   * Additional variants can be registered in
   * src/config/landingContent/index.ts.
   */
  REACT_APP_LANDING_VARIANT: string;
}

function toBoolean(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (value == null) return false;
  const normalized = String(value).trim().toLowerCase();
  return normalized === "true" || normalized === "1" || normalized === "yes";
}

/**
 * Returns a normalized, typed view of environment configuration.
 */
export function getRuntimeEnv(): EnvConfig {
  // window._env_ is injected at runtime via scripts (e.g., env-config.js/env.js)
  const winEnv: Record<string, unknown> =
    (typeof window !== "undefined"
      ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any)._env_
      : {}) || {};

  // import.meta.env is provided by Vite at build time
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const metaEnv: Record<string, unknown> = (import.meta as any)?.env ?? {};

  const getString = (key: string, fallback = ""): string => {
    const value = winEnv[key] ?? metaEnv[key];
    if (value == null) return fallback;
    return String(value);
  };

  return {
    REACT_APP_APPLICATION_DOMAIN: getString("REACT_APP_APPLICATION_DOMAIN"),
    REACT_APP_APPLICATION_CLIENT_ID: getString(
      "REACT_APP_APPLICATION_CLIENT_ID"
    ),
    REACT_APP_AUDIENCE: getString("REACT_APP_AUDIENCE"),
    REACT_APP_API_ROOT_URL: getString(
      "REACT_APP_API_ROOT_URL",
      "http://localhost:8000"
    ),
    REACT_APP_USE_AUTH0: toBoolean(
      winEnv["REACT_APP_USE_AUTH0"] ?? metaEnv["REACT_APP_USE_AUTH0"]
    ),
    REACT_APP_USE_ANALYZERS: toBoolean(
      winEnv["REACT_APP_USE_ANALYZERS"] ?? metaEnv["REACT_APP_USE_ANALYZERS"]
    ),
    REACT_APP_ALLOW_IMPORTS: toBoolean(
      winEnv["REACT_APP_ALLOW_IMPORTS"] ?? metaEnv["REACT_APP_ALLOW_IMPORTS"]
    ),
    REACT_APP_POSTHOG_API_KEY: getString("REACT_APP_POSTHOG_API_KEY"),
    REACT_APP_POSTHOG_HOST: getString(
      "REACT_APP_POSTHOG_HOST",
      "https://us.i.posthog.com"
    ),
    REACT_APP_LANDING_VARIANT: getString(
      "REACT_APP_LANDING_VARIANT",
      "default"
    ),
  };
}
