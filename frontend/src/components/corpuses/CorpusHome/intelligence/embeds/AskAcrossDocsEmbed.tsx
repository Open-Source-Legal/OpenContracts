/**
 * AskAcrossDocsEmbed — CAML embed wrapper for the cross-document question chips.
 *
 * Marker: ``[component:ask-across-docs]``.
 * Routes through ``CamlEmbedContext.onAskQuestion`` (bound to the article's
 * existing floating chat), so the chips feed that chat rather than introducing a
 * second chat affordance. Renders nothing if no handler is available — notably
 * the CamlArticleEditor preview, which provides only ``corpusId`` (it has no
 * live chat), so this embed is intentionally absent there.
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
