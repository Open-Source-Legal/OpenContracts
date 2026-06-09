/**
 * AskAcrossDocsEmbed — CAML embed wrapper for the cross-document question chips.
 *
 * Marker: ``[component:ask-across-docs]``.
 * Routes through ``CamlEmbedContext.onAskQuestion`` (bound to the article's
 * existing floating chat), so the chips feed that chat rather than introducing a
 * second chat affordance. Renders nothing if no handler is available (e.g. a
 * read-only preview without chat wiring).
 */
import React from "react";

import { SuggestedQuestions } from "../SuggestedQuestions";
import { useCamlEmbedContext } from "../../../caml/CamlEmbedContext";

export const AskAcrossDocsEmbed: React.FC<
  Record<string, string | undefined>
> = () => {
  const { onAskQuestion } = useCamlEmbedContext();
  if (!onAskQuestion) return null;
  return <SuggestedQuestions onAskQuestion={onAskQuestion} />;
};
