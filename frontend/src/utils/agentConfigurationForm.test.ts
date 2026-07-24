import { describe, expect, it } from "vitest";

import { computePreferredLlmUpdateArgs } from "./agentConfigurationForm";

describe("computePreferredLlmUpdateArgs", () => {
  it("sends the trimmed value and no clear flag when setting a new override", () => {
    expect(computePreferredLlmUpdateArgs("openai:gpt-4o", null)).toEqual({
      preferredLlm: "openai:gpt-4o",
      clearPreferredLlm: false,
    });
  });

  it("trims surrounding whitespace from a non-empty value", () => {
    expect(computePreferredLlmUpdateArgs("  openai:gpt-4o  ", null)).toEqual({
      preferredLlm: "openai:gpt-4o",
      clearPreferredLlm: false,
    });
  });

  it("sends clearPreferredLlm when clearing an existing override", () => {
    expect(computePreferredLlmUpdateArgs("", "openai:gpt-4o")).toEqual({
      preferredLlm: undefined,
      clearPreferredLlm: true,
    });
  });

  it("does not clear when the field is left empty and there was no prior override", () => {
    expect(computePreferredLlmUpdateArgs("", null)).toEqual({
      preferredLlm: undefined,
      clearPreferredLlm: false,
    });
    expect(computePreferredLlmUpdateArgs("", undefined)).toEqual({
      preferredLlm: undefined,
      clearPreferredLlm: false,
    });
  });

  it("treats a whitespace-only current value as no prior override", () => {
    expect(computePreferredLlmUpdateArgs("", "   ")).toEqual({
      preferredLlm: undefined,
      clearPreferredLlm: false,
    });
  });

  it("treats a whitespace-only form value as clearing when there was a prior override", () => {
    expect(computePreferredLlmUpdateArgs("   ", "openai:gpt-4o")).toEqual({
      preferredLlm: undefined,
      clearPreferredLlm: true,
    });
  });

  it("changes an existing override to a different value without setting the clear flag", () => {
    expect(
      computePreferredLlmUpdateArgs(
        "anthropic:claude-sonnet-5",
        "openai:gpt-4o"
      )
    ).toEqual({
      preferredLlm: "anthropic:claude-sonnet-5",
      clearPreferredLlm: false,
    });
  });

  it("re-sends the same value unchanged without setting the clear flag", () => {
    expect(
      computePreferredLlmUpdateArgs("openai:gpt-4o", "openai:gpt-4o")
    ).toEqual({
      preferredLlm: "openai:gpt-4o",
      clearPreferredLlm: false,
    });
  });
});
