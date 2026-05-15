/**
 * Helper for emitting the markdown-link mention grammar from
 * docs/architecture/rich_mentions.md.
 *
 *   Global agents:        [@<slug>](/agents/<slug>)
 *   Corpus-scoped agents: [@<slug>](/c/<corpus-slug>/agents/<slug>)
 *
 * The backend mention extractor parses these markdown links to resolve
 * agent references in chat messages, so the format must stay in lockstep
 * with `opencontractserver.llms.agents.mention_extractor._classify_url`.
 */

export interface AgentForLink {
  slug: string;
  scope: "GLOBAL" | "CORPUS";
  corpus?: { slug: string } | null;
}

export interface AgentMentionLink {
  /** Display label inserted into the textarea, e.g. `@research-bot`. */
  label: string;
  /** Relative URL the markdown link points at. */
  url: string;
  /** Fully-formed markdown link ready to splice into the message body. */
  markdown: string;
}

export function buildAgentMentionLink(agent: AgentForLink): AgentMentionLink {
  const label = `@${agent.slug}`;
  const url =
    agent.scope === "GLOBAL" || !agent.corpus
      ? `/agents/${agent.slug}`
      : `/c/${agent.corpus.slug}/agents/${agent.slug}`;
  return { label, url, markdown: `[${label}](${url})` };
}
