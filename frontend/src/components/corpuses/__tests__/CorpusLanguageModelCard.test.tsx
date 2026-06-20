import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { toast } from "react-toastify";

import { CorpusLanguageModelCard } from "../CorpusLanguageModelCard";
import {
  GET_LLM_PROVIDERS,
  GET_SYSTEM_DEFAULT_LLM,
} from "../../../graphql/queries";
import { UPDATE_CORPUS } from "../../../graphql/mutations";

vi.mock("react-toastify", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const providersMock = {
  request: { query: GET_LLM_PROVIDERS },
  result: {
    data: {
      pipelineComponents: {
        llmProviders: [
          {
            className: "x.AnthropicProvider",
            name: "anthropic",
            title: "Anthropic",
            providerKey: "anthropic",
            supportedModels: ["claude-opus-4-6"],
            requiresApiKey: true,
            enabled: true,
          },
          // Disabled provider must be filtered out of the picker.
          {
            className: "x.DisabledProvider",
            name: "disabled",
            title: "Disabled",
            providerKey: "disabled",
            supportedModels: ["should-not-render"],
            requiresApiKey: false,
            enabled: false,
          },
        ],
      },
    },
  },
};

const defaultLlmMock = {
  request: { query: GET_SYSTEM_DEFAULT_LLM },
  result: { data: { pipelineSettings: { defaultLlm: "openai:gpt-4o" } } },
};

const SELECTED_SPEC = "anthropic:claude-opus-4-6";

describe("CorpusLanguageModelCard", () => {
  it("loads providers, hides disabled ones, and saves the selected model", async () => {
    const updateMock = {
      request: {
        query: UPDATE_CORPUS,
        variables: { id: "corpus-1", preferredLlm: SELECTED_SPEC },
      },
      result: { data: { updateCorpus: { ok: true, message: "ok" } } },
    };

    render(
      <MockedProvider
        mocks={[providersMock, defaultLlmMock, updateMock]}
        addTypename={false}
      >
        <CorpusLanguageModelCard
          corpusId="corpus-1"
          initialPreferredLlm={null}
          canUpdate
        />
      </MockedProvider>
    );

    expect(screen.getByText("Language Model")).toBeInTheDocument();

    // Enabled provider's chip renders; disabled provider's does not.
    const chip = await screen.findByRole("button", {
      name: "claude-opus-4-6",
    });
    expect(
      screen.queryByRole("button", { name: "should-not-render" })
    ).toBeNull();

    fireEvent.click(chip);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Updated corpus language model"
      )
    );
  });

  it("rolls back and toasts on mutation error", async () => {
    const errorMock = {
      request: {
        query: UPDATE_CORPUS,
        variables: { id: "corpus-1", preferredLlm: SELECTED_SPEC },
      },
      error: new Error("network boom"),
    };

    render(
      <MockedProvider
        mocks={[providersMock, defaultLlmMock, errorMock]}
        addTypename={false}
      >
        <CorpusLanguageModelCard
          corpusId="corpus-1"
          initialPreferredLlm={null}
          canUpdate
        />
      </MockedProvider>
    );

    const chip = await screen.findByRole("button", {
      name: "claude-opus-4-6",
    });
    fireEvent.click(chip);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("network boom")
    );
  });

  it("rolls back and toasts when the server returns ok: false", async () => {
    const notOkMock = {
      request: {
        query: UPDATE_CORPUS,
        variables: { id: "corpus-1", preferredLlm: SELECTED_SPEC },
      },
      result: { data: { updateCorpus: { ok: false, message: "nope" } } },
    };

    render(
      <MockedProvider
        mocks={[providersMock, defaultLlmMock, notOkMock]}
        addTypename={false}
      >
        <CorpusLanguageModelCard
          corpusId="corpus-1"
          initialPreferredLlm={null}
          canUpdate
        />
      </MockedProvider>
    );

    const chip = await screen.findByRole("button", {
      name: "claude-opus-4-6",
    });
    fireEvent.click(chip);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("nope"));
  });

  it("clears the draft to inherit the default", async () => {
    render(
      <MockedProvider
        mocks={[providersMock, defaultLlmMock]}
        addTypename={false}
      >
        <CorpusLanguageModelCard
          corpusId="corpus-1"
          initialPreferredLlm={SELECTED_SPEC}
          canUpdate
        />
      </MockedProvider>
    );

    const clearBtn = await screen.findByRole("button", {
      name: /clear \(use default\)/i,
    });
    fireEvent.click(clearBtn);

    // Clearing empties the draft, so the Clear button hides itself.
    expect(
      screen.queryByRole("button", { name: /clear \(use default\)/i })
    ).toBeNull();
  });

  it("renders read-only (no Save button) when canUpdate is false", () => {
    render(
      <MockedProvider mocks={[defaultLlmMock]} addTypename={false}>
        <CorpusLanguageModelCard
          corpusId="corpus-1"
          initialPreferredLlm="anthropic:claude-haiku-4-5"
          canUpdate={false}
        />
      </MockedProvider>
    );

    expect(screen.getByText("Language Model")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
