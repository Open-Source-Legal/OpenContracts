/**
 * Shared helpers for the agent-configuration create/update forms
 * (GlobalAgentManagement, CorpusAgentManagement) so the
 * AgentConfigurationService contract for `preferred_llm` is encoded once.
 */

/**
 * AgentConfigurationService.update_agent's contract (config/graphql/
 * agent_mutations.py): preferred_llm=None means "leave unchanged";
 * clear_preferred_llm=True is the only way to reset the override back to
 * the corpus/system default (an empty string would fail the model's
 * validation). So we only ever send a non-empty preferredLlm or the
 * clear flag — never both, and never an empty-string preferredLlm.
 */
export function computePreferredLlmUpdateArgs(
  formPreferredLlm: string,
  currentPreferredLlm: string | null | undefined
): { preferredLlm: string | undefined; clearPreferredLlm: boolean } {
  const trimmedLlm = formPreferredLlm.trim();
  const hadPreferredLlm = Boolean(currentPreferredLlm?.trim());
  const clearPreferredLlm = trimmedLlm === "" && hadPreferredLlm;

  return {
    preferredLlm: trimmedLlm || undefined,
    clearPreferredLlm,
  };
}
