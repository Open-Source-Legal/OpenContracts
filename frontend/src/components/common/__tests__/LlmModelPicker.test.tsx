import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LlmModelPicker } from "../LlmModelPicker";
import type { LlmProviderOption } from "../../../types/graphql-api";

const providers: LlmProviderOption[] = [
  {
    className: "opencontractserver...AnthropicProvider",
    name: "anthropic",
    title: "Anthropic",
    providerKey: "anthropic",
    supportedModels: ["claude-opus-4-6", "claude-haiku-4-5"],
    requiresApiKey: true,
  },
];

describe("LlmModelPicker", () => {
  it("emits a provider:model spec when a suggested-model chip is clicked", () => {
    const onChange = vi.fn();
    render(
      <LlmModelPicker value="" onChange={onChange} providers={providers} />
    );
    fireEvent.click(screen.getByRole("button", { name: "claude-haiku-4-5" }));
    expect(onChange).toHaveBeenCalledWith("anthropic:claude-haiku-4-5");
  });

  it("shows the inherited default when value is empty", () => {
    render(
      <LlmModelPicker
        value=""
        onChange={() => {}}
        providers={providers}
        inheritedSpec="openai:gpt-4o"
        inheritedLabel="Inherited system default"
      />
    );
    const hint = screen.getByTestId("llm-inherited-hint");
    expect(hint).toHaveTextContent("Inherited system default");
    expect(hint).toHaveTextContent("openai:gpt-4o");
  });

  it("falls back to a generic hint when no inherited spec is provided", () => {
    render(<LlmModelPicker value="" onChange={() => {}} providers={[]} />);
    expect(screen.getByTestId("llm-inherited-hint")).toHaveTextContent(
      "Leave empty to inherit the server default model."
    );
  });

  it("does not fire onChange when a disabled chip is clicked", () => {
    const onChange = vi.fn();
    render(
      <LlmModelPicker
        value=""
        onChange={onChange}
        providers={providers}
        disabled
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "claude-haiku-4-5" }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("hides the inherited hint once a value is set", () => {
    render(
      <LlmModelPicker
        value="anthropic:claude-opus-4-6"
        onChange={() => {}}
        providers={providers}
        inheritedSpec="openai:gpt-4o"
      />
    );
    expect(screen.queryByTestId("llm-inherited-hint")).toBeNull();
  });
});
