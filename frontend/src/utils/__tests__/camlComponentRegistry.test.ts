import { describe, it, expect } from "vitest";

import { CAML_COMPONENTS } from "../camlComponentRegistry";
import { resolveComponentMarker } from "../camlComponents";
import { InsightPanelEmbed } from "../../components/corpuses/CorpusHome/intelligence/embeds/InsightPanelEmbed";
import { DocumentGraphEmbed } from "../../components/corpuses/CorpusHome/intelligence/embeds/DocumentGraphEmbed";
import { AskAcrossDocsEmbed } from "../../components/corpuses/CorpusHome/intelligence/embeds/AskAcrossDocsEmbed";

describe("CAML_COMPONENTS registry", () => {
  it("registers the corpus-intelligence embeds under their marker names", () => {
    expect(CAML_COMPONENTS["insight-panel"]).toBe(InsightPanelEmbed);
    expect(CAML_COMPONENTS["document-graph"]).toBe(DocumentGraphEmbed);
    expect(CAML_COMPONENTS["ask-across-docs"]).toBe(AskAcrossDocsEmbed);
  });

  it("resolves intelligence markers to React elements", () => {
    for (const type of ["insight-panel", "document-graph", "ask-across-docs"]) {
      const el = resolveComponentMarker(`[component:${type}]`, CAML_COMPONENTS);
      expect(el).not.toBeNull();
    }
  });

  it("returns null for an unregistered marker type", () => {
    expect(
      resolveComponentMarker("[component:not-a-real-embed]", CAML_COMPONENTS)
    ).toBeNull();
  });
});
