import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ApolloClient,
  ApolloLink,
  ApolloProvider,
  InMemoryCache,
  Observable,
  Operation,
} from "@apollo/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backendUserObj } from "../../graphql/cache";
import { AutomationCredentialManagement } from "./AutomationCredentialManagement";
import { GlobalSettingsPanel } from "./GlobalSettingsPanel";

const admin = {
  id: btoa("UserType:7"),
  email: "admin@example.test",
  isSuperuser: true,
};
const cliCredential = {
  id: "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  name: "CLI importer",
  userId: "7",
  username: "service",
  scopes: ["corpus:read"],
  corpusIds: ["42"],
  status: "active",
  createdAt: "2026-09-01T00:00:00Z",
  expiresAt: "2026-10-01T00:00:00Z",
  revokedAt: null,
  rotatedAt: null,
};
const issuedToken = `${cliCredential.id}.one-time-test-secret`;

function setup({
  failMutation = false,
  failRotate = false,
  detailStatus = "active",
  ownerId = "7",
} = {}) {
  let revoked = false;
  const requests = vi.fn((operation: Operation) => {
    switch (operation.operationName) {
      case "AutomationCredentials":
        return {
          automationCredentials: {
            totalCount: 2,
            items: [
              operation.variables.offset === 0
                ? { ...cliCredential, status: revoked ? "revoked" : "active" }
                : {
                    ...cliCredential,
                    id: "second-id",
                    name: "Other credential",
                  },
            ],
          },
        };
      case "AutomationCredentialScopes":
        return {
          automationCredentialScopes: ["corpus:read", "document:import"],
        };
      case "AutomationCredential":
        return {
          automationCredential: {
            ...cliCredential,
            userId: ownerId,
            status: revoked ? "revoked" : detailStatus,
          },
        };
      case "AutomationCredentialChoices":
        return {
          automationCredentialChoices: {
            totalCount: 1,
            items: [
              operation.variables.kind === "principal"
                ? { id: "7", label: "service" }
                : { id: "42", label: "Contracts" },
            ],
          },
        };
      case "MintAutomationCredential":
        return { mintAutomationCredential: { token: issuedToken } };
      case "RotateAutomationCredential":
        if (failRotate) revoked = true;
        return { rotateAutomationCredential: { token: issuedToken } };
      case "RevokeAutomationCredential":
        revoked = true;
        return {
          revokeAutomationCredential: {
            id: cliCredential.id,
            status: "revoked",
          },
        };
      default:
        throw new Error(`Unexpected operation: ${operation.operationName}`);
    }
  });
  const client = new ApolloClient({
    cache: new InMemoryCache(),
    link: new ApolloLink(
      (operation) =>
        new Observable((observer) => {
          const result = requests(operation);
          Promise.resolve().then(() => {
            if (
              (failMutation &&
                operation.operationName === "MintAutomationCredential") ||
              (failRotate &&
                operation.operationName === "RotateAutomationCredential")
            )
              observer.error(new Error("Denied"));
            else {
              observer.next({ data: result });
              observer.complete();
            }
          });
        })
    ),
  });
  function AdminTestWrapper() {
    return (
      <ApolloProvider client={client}>
        <MemoryRouter>
          <AutomationCredentialManagement />
        </MemoryRouter>
      </ApolloProvider>
    );
  }
  return { ...render(<AdminTestWrapper />), requests, client };
}

async function fillMint() {
  await userEvent.click(screen.getByRole("button", { name: "New credential" }));
  await userEvent.type(screen.getByLabelText("Name"), "Nightly import");
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "corpus:read" })
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Contracts (ID 42)" })
  );
}

beforeEach(() => {
  backendUserObj(admin);
  localStorage.clear();
  sessionStorage.clear();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});
afterEach(() => {
  cleanup();
  backendUserObj(null);
  vi.restoreAllMocks();
});

describe("Automation credential management", () => {
  it("links the page from admin settings", async () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<GlobalSettingsPanel />} />
          <Route
            path="/automation-credentials"
            element={<p>Credential management destination</p>}
          />
        </Routes>
      </MemoryRouter>
    );
    await userEvent.click(
      screen.getByTestId("settings-card-automation-credentials")
    );
    expect(screen.getByText("Credential management destination")).toBeVisible();
  });

  it("does not load management data for anonymous visitors", () => {
    backendUserObj(null);
    const { requests } = setup();
    expect(screen.getByRole("alert")).toHaveTextContent("login is required");
    expect(
      screen.queryByRole("button", { name: "New credential" })
    ).not.toBeInTheDocument();
    expect(requests).not.toHaveBeenCalled();
  });

  it("lets regular users mint for their account without admin controls", async () => {
    backendUserObj({ ...admin, isSuperuser: false });
    const { requests } = setup();
    await fillMint();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Allow all corpuses (including future corpuses)")
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Back to admin settings" })
    ).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Mint credential" })
    );
    expect(await screen.findByText(issuedToken)).toBeVisible();
    expect(
      requests.mock.calls.find(
        ([op]) => op.operationName === "MintAutomationCredential"
      )?.[0].variables
    ).toEqual({
      name: "Nightly import",
      scopes: ["corpus:read"],
      corpusIds: ["42"],
      allCorpuses: false,
      expiresDays: 30,
    });
  });

  it("lets admins revoke another user's credential without offering rotation", async () => {
    setup({ ownerId: "8" });
    await userEvent.click(
      await screen.findByRole("button", { name: "Inspect CLI importer" })
    );
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).queryByRole("button", { name: "Rotate" })
    ).not.toBeInTheDocument();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Revoke" })
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Confirm revoke" })
    );
    expect(await screen.findByText("revoked")).toBeVisible();
    expect(screen.queryByText(issuedToken)).not.toBeInTheDocument();
  });

  it("requires explicit inputs and keeps a minted token only until dismissed", async () => {
    const { requests, client, unmount } = setup();
    await fillMint();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(
      requests.mock.calls.some(([op]) => op.variables.kind === "principal")
    ).toBe(false);
    const mint = screen.getByRole("button", { name: "Mint credential" });
    const days = screen.getByLabelText("Expires in days");
    expect(days).toHaveValue(30);
    await userEvent.clear(days);
    await userEvent.type(days, "0");
    expect(mint).toBeDisabled();
    await userEvent.clear(days);
    await userEvent.type(days, "30");
    await userEvent.click(
      screen.getByRole("checkbox", { name: "corpus:read" })
    );
    expect(mint).toBeDisabled();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "corpus:read" })
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Contracts (ID 42)" })
    );
    expect(mint).toBeDisabled();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Contracts (ID 42)" })
    );
    await userEvent.click(mint);
    expect(await screen.findByText(issuedToken)).toBeVisible();
    const operation = requests.mock.calls.find(
      ([op]) => op.operationName === "MintAutomationCredential"
    )?.[0];
    expect(operation?.variables).toEqual({
      name: "Nightly import",
      scopes: ["corpus:read"],
      corpusIds: ["42"],
      allCorpuses: false,
      expiresDays: 30,
    });
    await userEvent.click(screen.getByRole("button", { name: "Copy token" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(issuedToken);
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(JSON.stringify(client.cache.extract())).not.toContain(issuedToken);
    expect(JSON.stringify(localStorage)).not.toContain(issuedToken);
    expect(JSON.stringify(sessionStorage)).not.toContain(issuedToken);
    await userEvent.click(
      screen.getByRole("button", { name: "Dismiss token" })
    );
    await waitFor(() =>
      expect(screen.queryByText(issuedToken)).not.toBeInTheDocument()
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Inspect CLI importer" })
    );
    expect(screen.queryByText(issuedToken)).not.toBeInTheDocument();
    unmount();
    setup();
    expect(await screen.findByText("CLI importer")).toBeInTheDocument();
    expect(screen.queryByText(issuedToken)).not.toBeInTheDocument();
  });

  it("sends explicit all-corpus access and presents a failed mint without exposing a token", async () => {
    const { requests } = setup({ failMutation: true });
    await fillMint();
    await userEvent.click(
      screen.getByRole("checkbox", {
        name: "Allow all corpuses (including future corpuses)",
      })
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Mint credential" })
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unable to complete"
    );
    const operation = requests.mock.calls.find(
      ([op]) => op.operationName === "MintAutomationCredential"
    )?.[0];
    expect(operation?.variables).toMatchObject({
      allCorpuses: true,
      corpusIds: null,
    });
    expect(screen.queryByText(issuedToken)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Nightly import");
  });

  it("inspects and rotates a CLI credential, clears its token on logout, and revokes after confirmation", async () => {
    const { requests, client } = setup();
    await userEvent.click(
      await screen.findByRole("button", { name: "Inspect CLI importer" })
    );
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(cliCredential.id)).toBeVisible();
    expect(within(dialog).getByText("42")).toBeVisible();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Rotate" })
    );
    expect(
      requests.mock.calls.filter(
        ([op]) => op.operationName === "RotateAutomationCredential"
      )
    ).toHaveLength(0);
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Confirm rotate" })
    );
    expect(await screen.findByText(issuedToken)).toBeVisible();
    expect(
      requests.mock.calls.find(
        ([op]) => op.operationName === "RotateAutomationCredential"
      )?.[0].variables
    ).toEqual({ id: cliCredential.id });
    expect(JSON.stringify(client.cache.extract())).not.toContain(issuedToken);
    act(() => {
      backendUserObj(null);
    });
    await waitFor(() =>
      expect(screen.queryByText(issuedToken)).not.toBeInTheDocument()
    );
    act(() => {
      backendUserObj(admin);
    });
    await userEvent.click(
      await screen.findByRole("button", { name: "Inspect CLI importer" })
    );
    dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Revoke" })
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Confirm revoke" })
    );
    expect(await screen.findByText("revoked")).toBeVisible();
    expect(
      requests.mock.calls.find(
        ([op]) => op.operationName === "RevokeAutomationCredential"
      )?.[0].variables
    ).toEqual({ id: cliCredential.id });
    expect(screen.queryByText(issuedToken)).not.toBeInTheDocument();
  });

  it("loads the next page of metadata instead of truncating the credential list", async () => {
    const { requests } = setup();
    await screen.findByText("CLI importer");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Other credential")).toBeVisible();
    expect(screen.queryByText("CLI importer")).not.toBeInTheDocument();
    expect(
      requests.mock.calls
        .filter(([op]) => op.operationName === "AutomationCredentials")
        .map(([op]) => op.variables.offset)
    ).toEqual([0, 1]);
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("inspects current status even when another administrator revoked a listed credential", async () => {
    const { requests } = setup({ detailStatus: "revoked" });
    await screen.findByText("active");
    await userEvent.click(
      screen.getByRole("button", { name: "Inspect CLI importer" })
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("revoked")).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: "Rotate" })
    ).toBeDisabled();
    expect(
      requests.mock.calls.find(
        ([op]) => op.operationName === "AutomationCredential"
      )?.[0].variables
    ).toEqual({ id: cliCredential.id });
  });

  it("refreshes the detail after a concurrent revocation makes rotation fail", async () => {
    const { requests } = setup({ failRotate: true });
    await userEvent.click(
      await screen.findByRole("button", { name: "Inspect CLI importer" })
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Rotate" })
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Confirm rotate" })
    );
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Unable to complete"
    );
    expect(await within(dialog).findByText("revoked")).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: "Rotate" })
    ).toBeDisabled();
    expect(
      requests.mock.calls.filter(
        ([op]) => op.operationName === "AutomationCredential"
      )
    ).toHaveLength(2);
    expect(screen.queryByText(issuedToken)).not.toBeInTheDocument();
  });
});
