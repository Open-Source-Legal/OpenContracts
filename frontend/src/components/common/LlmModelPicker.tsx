/**
 * LlmModelPicker — shared control for choosing a pydantic-ai model spec
 * ("{provider}:{model}", e.g. "anthropic:claude-opus-4-6").
 *
 * Renders a free-text spec input plus one-click "suggested model" chips grouped
 * by registered provider (sourced from the `pipelineComponents.llmProviders`
 * query). Used both by the admin System Settings screen (install-wide default
 * LLM) and the per-corpus Language Model setting. Centralising it keeps the two
 * surfaces in sync and avoids duplicating the chip-rendering logic.
 *
 * Presentational only: the caller owns the value, fetches the provider list,
 * and persists the result.
 */
import React, { useId } from "react";
import { Input } from "@os-legal/ui";

import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
// LlmProviderOption's canonical home is types/graphql-api.ts; import it (don't
// re-export) so there's a single import path for the type.
import type { LlmProviderOption } from "../../types/graphql-api";

export interface LlmModelPickerProps {
  /** Current model spec value ("provider:model"), or "" when unset. */
  value: string;
  onChange: (spec: string) => void;
  /** Registered providers + their suggested models. */
  providers: LlmProviderOption[];
  /** Optional field label rendered above the input. */
  label?: React.ReactNode;
  placeholder?: string;
  helperText?: React.ReactNode;
  /**
   * Spec that takes effect when `value` is empty (e.g. the install-wide default
   * a corpus inherits). When provided and `value` is blank, a hint shows what
   * model is actually in effect so users understand "leave empty = inherit".
   */
  inheritedSpec?: string | null;
  /** Label shown next to the inherited spec (default: "Currently inheriting"). */
  inheritedLabel?: string;
  /** Show an "(API key required)" badge per provider. */
  showApiKeyBadge?: boolean;
  disabled?: boolean;
  id?: string;
}

export const LlmModelPicker: React.FC<LlmModelPickerProps> = ({
  value,
  onChange,
  providers,
  label,
  placeholder = "e.g., anthropic:claude-opus-4-6",
  helperText,
  inheritedSpec,
  inheritedLabel = "Currently inheriting",
  showApiKeyBadge = false,
  disabled = false,
  id,
}) => {
  // Fall back to a render-unique id so two pickers on one page can't collide on
  // the label↔input association.
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const isEmpty = !value.trim();

  return (
    <div>
      {label && (
        <label
          htmlFor={fieldId}
          style={{
            display: "block",
            fontSize: "0.8125rem",
            fontWeight: 600,
            marginBottom: "0.375rem",
            color: OS_LEGAL_COLORS.textPrimary,
          }}
        >
          {label}
        </label>
      )}
      <Input
        id={fieldId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        fullWidth
      />

      {helperText && (
        <p
          style={{
            margin: "0.375rem 0 0",
            fontSize: "0.75rem",
            color: OS_LEGAL_COLORS.textSecondary,
          }}
        >
          {helperText}
        </p>
      )}

      {/* Only surface the "inherit" hint when the caller opts into the
          concept by passing `inheritedSpec` (even `null`). System Settings —
          the install-wide default, which has nothing higher to inherit —
          omits the prop entirely and so shows no hint. */}
      {isEmpty && inheritedSpec !== undefined && (
        <p
          data-testid="llm-inherited-hint"
          style={{
            margin: "0.375rem 0 0",
            fontSize: "0.75rem",
            color: OS_LEGAL_COLORS.textSecondary,
          }}
        >
          {inheritedSpec ? (
            <>
              {inheritedLabel}:{" "}
              <code style={{ color: OS_LEGAL_COLORS.textPrimary }}>
                {inheritedSpec}
              </code>
            </>
          ) : (
            "Leave empty to inherit the server default model."
          )}
        </p>
      )}

      {providers.length > 0 && (
        <div style={{ marginTop: "0.75rem" }}>
          <div
            style={{
              fontSize: "0.8125rem",
              fontWeight: 600,
              marginBottom: "0.25rem",
              color: OS_LEGAL_COLORS.textPrimary,
            }}
          >
            Registered Providers &amp; Suggested Models:
          </div>
          {providers.map((provider) => {
            const providerKey = provider.providerKey || "";
            const models = (provider.supportedModels || []).filter(
              (m): m is string => Boolean(m)
            );
            return (
              <div
                key={provider.className || provider.name || providerKey}
                style={{ marginTop: "0.75rem" }}
              >
                <div
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    marginBottom: "0.375rem",
                  }}
                >
                  {provider.title || provider.name}
                  {showApiKeyBadge && provider.requiresApiKey && (
                    <span
                      style={{
                        marginLeft: 6,
                        fontSize: "0.75rem",
                        fontWeight: 400,
                        color: OS_LEGAL_COLORS.textSecondary,
                      }}
                    >
                      (API key required)
                    </span>
                  )}
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "0.375rem",
                  }}
                >
                  {models.length > 0 ? (
                    models.map((model) => {
                      const spec = providerKey
                        ? `${providerKey}:${model}`
                        : model;
                      // Trim so a stray trailing space in the free-text input
                      // still highlights the matching chip.
                      const selected = value.trim() === spec;
                      return (
                        <button
                          key={spec}
                          type="button"
                          aria-pressed={selected}
                          disabled={disabled}
                          // Guard in the handler too (not just the native
                          // `disabled` attribute) so the no-op is the
                          // component's own contract, independent of the
                          // element type.
                          onClick={() => {
                            if (disabled) return;
                            onChange(spec);
                          }}
                          style={{
                            padding: "0.25rem 0.625rem",
                            fontSize: "0.75rem",
                            cursor: disabled ? "not-allowed" : "pointer",
                            borderRadius: "9999px",
                            background: selected
                              ? OS_LEGAL_COLORS.selectedBg
                              : OS_LEGAL_COLORS.surfaceHover,
                            border: `1px solid ${
                              selected
                                ? OS_LEGAL_COLORS.selectedBorder
                                : OS_LEGAL_COLORS.border
                            }`,
                            color: OS_LEGAL_COLORS.textPrimary,
                            opacity: disabled ? 0.6 : 1,
                          }}
                        >
                          {model}
                        </button>
                      );
                    })
                  ) : (
                    <span
                      style={{
                        fontSize: "0.75rem",
                        color: OS_LEGAL_COLORS.textSecondary,
                      }}
                    >
                      No suggested models — enter a spec manually
                      {providerKey ? ` (prefix: ${providerKey}:)` : ""}.
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default LlmModelPicker;
