import React from "react";
import { webcrypto } from "node:crypto";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useAuth0 } from "@auth0/auth0-react";
import { BrowserRouter } from "react-router-dom";
import {
  ApolloClient,
  ApolloProvider,
  ApolloLink,
  InMemoryCache,
  Observable,
} from "@apollo/client";
import { screen } from "@testing-library/react";
import { toast } from "react-toastify";
import { Auth0ProviderWithHistory } from "./Auth0ProviderWithHistory";
import { CentralRouteManager } from "../routing/CentralRouteManager";
import { AuthGate } from "../components/auth/AuthGate";
import { useAuthenticated } from "../hooks/useAuthenticated";
import { authLink } from "../graphql/authLink";
import { authInitCompleteVar, authStatusVar } from "../graphql/cache";
import { clearAuthSession } from "./authSession";
import { navigationCircuitBreaker } from "./navigationCircuitBreaker";
import { act, cleanup, renderHook, waitFor } from "../test-utils/renderHook";

vi.mock("react-toastify", () => ({
  toast: { error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock("../components/widgets/ModernLoadingDisplay", () => ({
  ModernLoadingDisplay: () => <div>Initializing OpenContracts</div>,
}));

const identity = { sub: "auth0|alice", name: "Alice" };
const tokenRequest = vi.fn<typeof fetch>();
const audience = "https://api.example.test";

function storeTransaction() {
  sessionStorage.setItem(
    "a0.spajs.txs.callback-test",
    JSON.stringify({
      nonce: "test-nonce",
      code_verifier: "test-code-verifier",
      state: "oauth-state",
      scope: "openid profile email offline_access",
      audience,
      redirect_uri: window.location.origin,
      appState: { returnTo: "/documents" },
    })
  );
}

function tokenResponse() {
  const now = Math.floor(Date.now() / 1000);
  const encode = (value: object) =>
    btoa(JSON.stringify(value))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  const idToken = [
    encode({ alg: "RS256", typ: "JWT" }),
    encode({
      ...identity,
      iss: "https://example.auth0.com/",
      aud: "callback-test",
      iat: now,
      exp: now + 3600,
      nonce: "test-nonce",
    }),
    "test-signature",
  ].join(".");
  return new Response(
    JSON.stringify({
      access_token: "access-token",
      refresh_token: "refresh-token",
      id_token: idToken,
      token_type: "Bearer",
      expires_in: 3600,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}
const me = {
  id: "alice",
  email: "alice@example.test",
  username: "alice",
  slug: "alice",
  name: "Alice",
  firstName: "Alice",
  lastName: "",
  phone: "",
  isSuperuser: false,
  isUsageCapped: false,
  canImportCorpus: false,
  isProfilePublic: false,
  profileHeadline: "",
  profileAboutMarkdown: "",
  profileLinksMarkdown: "",
};

function SessionStatus() {
  const { error } = useAuth0();
  const authenticated = useAuthenticated();
  return (
    <div>
      {error && <span>{error.message}</span>}
      {authenticated ? "Signed in" : "Signed out"}
    </div>
  );
}

function setup() {
  const requested = vi.fn();
  const client = new ApolloClient({
    cache: new InMemoryCache(),
    link: ApolloLink.from([
      authLink,
      new ApolloLink(
        (operation) =>
          new Observable((observer) => {
            requested(operation.getContext().headers?.Authorization);
            observer.next({ data: { me } });
            observer.complete();
          })
      ),
    ]),
  });
  // Keep the real SDK provider, BrowserRouter and route manager: mocking
  // useAuth0 or navigation hides the child-before-parent effect ordering.
  const view = renderHook(() => null, {
    wrapper: () => (
      <BrowserRouter>
        <Auth0ProviderWithHistory
          domain="example.auth0.com"
          clientId="callback-test"
          useRefreshTokens
          useRefreshTokensFallback
          authorizationParams={{
            redirect_uri: window.location.origin,
            audience,
          }}
        >
          <ApolloProvider client={client}>
            <CentralRouteManager />
            <AuthGate useAuth0 audience={audience}>
              <SessionStatus />
            </AuthGate>
          </ApolloProvider>
        </Auth0ProviderWithHistory>
      </BrowserRouter>
    ),
  });
  return { ...view, requested };
}

beforeEach(async () => {
  vi.clearAllMocks();
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("fetch", tokenRequest);
  tokenRequest.mockReset();
  tokenRequest.mockRejectedValue(new Error("Unexpected token request"));
  sessionStorage.clear();
  for (const cookie of document.cookie.split(";")) {
    document.cookie = `${cookie.split("=")[0].trim()}=; Max-Age=0; Path=/`;
  }
  clearAuthSession();
  // Let the previous session's asynchronous cache cleanup settle.
  await act(async () => {});
  authStatusVar("LOADING");
  authInitCompleteVar(false);
  navigationCircuitBreaker.reset();
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("Auth0 callback initialization", () => {
  it("consumes code and state before routing, then validates the backend session", async () => {
    const callbackSearch = "?code=authorization-code&state=oauth-state";
    window.history.replaceState({}, "", "/" + callbackSearch);
    storeTransaction();
    let finishCallback!: (response: Response) => void;
    const callbackPending = new Promise<Response>((resolve) => {
      finishCallback = resolve;
    });
    tokenRequest.mockReturnValue(callbackPending);

    const app = setup();
    await waitFor(() => expect(tokenRequest).toHaveBeenCalledTimes(1));
    expect(tokenRequest.mock.calls[0][0]).toBe(
      "https://example.auth0.com/oauth/token"
    );
    const body = new URLSearchParams(
      tokenRequest.mock.calls[0][1]?.body as string
    );
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("code")).toBe("authorization-code");
    expect(body.get("code_verifier")).toBe("test-code-verifier");
    expect(window.location.search).toBe(callbackSearch);
    expect(app.requested).not.toHaveBeenCalled();
    expect(screen.getByText("Initializing OpenContracts")).toBeInTheDocument();

    await act(async () => finishCallback(tokenResponse()));
    await waitFor(() =>
      expect(screen.getByText("Signed in")).toBeInTheDocument()
    );
    expect(app.requested).toHaveBeenCalledWith("Bearer access-token");
    expect(window.location.pathname).toBe("/documents");
    expect(window.location.search).not.toMatch(/code=|state=/);
  });

  it("surfaces an OAuth error before cleaning up callback parameters", async () => {
    window.history.replaceState(
      {},
      "",
      "/?error=access_denied&error_description=Login+denied&state=oauth-state"
    );
    storeTransaction();

    const app = setup();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(tokenRequest).not.toHaveBeenCalled();
    expect(screen.getByText("Login denied")).toBeInTheDocument();
    expect(screen.getByText("Signed out")).toBeInTheDocument();
    expect(app.requested).not.toHaveBeenCalled();
    expect(window.location.search).not.toMatch(
      /error=|error_description=|state=/
    );
  });

  it("restores an ordinary page without requiring an Auth0 session", async () => {
    const app = setup();
    await waitFor(() =>
      expect(screen.getByText("Signed out")).toBeInTheDocument()
    );
    expect(tokenRequest).not.toHaveBeenCalled();
    expect(app.requested).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });
});
