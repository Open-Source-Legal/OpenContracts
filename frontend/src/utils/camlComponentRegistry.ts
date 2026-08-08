/**
 * Shared CAML component registry.
 *
 * Maps component type names (used in `[component:TYPE ...]` markers) to their
 * React component implementations. Both `CamlArticleEditor` and
 * `CorpusArticleView` import this single registry so additions are reflected
 * in both the editor preview and the published article view.
 */
import { ExtractGridEmbed } from "../components/extracts/ExtractGridEmbed";
import { InsightPanelEmbed } from "../components/corpuses/CorpusHome/intelligence/embeds/InsightPanelEmbed";
import { DocumentGraphEmbed } from "../components/corpuses/CorpusHome/intelligence/embeds/DocumentGraphEmbed";
import { GovernanceGraphEmbed } from "../components/corpuses/CorpusHome/intelligence/embeds/GovernanceGraphEmbed";
import { AskAcrossDocsEmbed } from "../components/corpuses/CorpusHome/intelligence/embeds/AskAcrossDocsEmbed";
import { CollectionDataStoryEmbed } from "../components/corpuses/CorpusHome/intelligence/embeds/CollectionDataStoryEmbed";
import { ResearchFindingsEmbed } from "../components/corpuses/CorpusHome/intelligence/embeds/ResearchFindingsEmbed";
import type { CamlComponentRegistry } from "./camlComponents";

export const CAML_COMPONENTS: CamlComponentRegistry = {
  "extract-grid": ExtractGridEmbed,
  // Corpus Intelligence embeds — corpus id + chat/explore callbacks come from
  // CamlEmbedContext (provided by CorpusArticleView / the editor preview).
  "insight-panel": InsightPanelEmbed,
  "collection-datastory": CollectionDataStoryEmbed,
  "document-graph": DocumentGraphEmbed,
  "governance-graph": GovernanceGraphEmbed,
  "ask-across-docs": AskAcrossDocsEmbed,
  // Emitted by ResearchReportService.finalize when a run recorded structured
  // findings; renders the takeaway cards above the written report.
  "research-findings": ResearchFindingsEmbed,
};
