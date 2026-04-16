/**
 * Use this file as a spot for small utility methods used throughout your
 * application.
 */
import _ from "lodash";

import { TokenId } from "../types";
import {
  RelationGroup,
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "./types/annotations";
import { PDFPageInfo } from "./types/pdf";

export function annotationSelectedViaRelationship(
  this_annotation: ServerTokenAnnotation | ServerSpanAnnotation,
  annotations: (ServerTokenAnnotation | ServerSpanAnnotation)[],
  relation: RelationGroup
): "SOURCE" | "TARGET" | "" {
  // console.log("this_annotation", this_annotation);
  // console.log("annotations", annotations);
  // console.log("relation", relation);

  let source_annotations = _.intersectionWith(
    annotations,
    relation.sourceIds,
    ({ id }, annotationId) => id === annotationId
  );

  // console.log("source_annotations", source_annotations);

  let target_annotations = _.intersectionWith(
    annotations,
    relation.targetIds,
    ({ id }, annotationId) => id === annotationId
  );

  // console.log("target_annotations", target_annotations)

  if (_.find(source_annotations, { id: this_annotation.id })) {
    return "SOURCE";
  } else if (_.find(target_annotations, { id: this_annotation.id })) {
    return "TARGET";
  } else {
    return "";
  }
}

// Given an array of TokenIds, which is what Pawls returns when we annotate tokens,
// Look up those token indices in the page's token array and then append those tokens
// together, separating by spaces. A more sophisticated approach could inspect token
// y-positions to insert newlines, but space-joining is sufficient for current usage.
export const convertAnnotationTokensToText = (
  pages: PDFPageInfo[] | undefined,
  page: number,
  tokens: TokenId[]
): string => {
  let page_tokens = pages ? pages[page].tokens : [];
  let token_indices = tokens.map((token) => token.tokenIndex);

  return page_tokens
    .filter((token, index) => token_indices.includes(index))
    .reduce<string>((acc, cur) => {
      // Handle image tokens and tokens with missing/null text gracefully
      const text = cur?.text ?? "";
      if (!text) {
        return acc;
      }
      return acc.length > 0 ? acc + " " + text : text;
    }, "");
};

interface CreateTokenStringSearchProps {
  doc_text: string;
  page_text_map: Record<number, string>;
  string_index_token_map: Record<number, TokenId>;
}

export const createTokenStringSearch = (
  pages: PDFPageInfo[]
): CreateTokenStringSearchProps => {
  let token_map: Record<number, TokenId> = {};
  let aggregate_text = "";
  let page_text_map: Record<number, string> = {};

  for (var p = 0; p < pages.length; p++) {
    let page = pages[p];
    let page_text = "";

    for (var i = 0; i < page.tokens.length; i++) {
      const token = page.tokens[i];
      // Handle image tokens and tokens with missing/null text gracefully
      // Image tokens have is_image=true and text="" or undefined
      const text = token?.text ?? "";

      // Skip tokens with no text (e.g., image tokens)
      if (!text) {
        continue;
      }

      if (page_text.length !== 0) {
        page_text += " ";
        aggregate_text += " ";
      }
      for (var j = 0; j < text.length; j++) {
        token_map[aggregate_text.length] = {
          tokenIndex: i,
          pageIndex: p,
        };
        aggregate_text += text[j];
        page_text += text[j];
      }
    }

    page_text_map[p] = page_text;
  }

  return {
    doc_text: aggregate_text,
    page_text_map: page_text_map,
    string_index_token_map: token_map,
  };
};
