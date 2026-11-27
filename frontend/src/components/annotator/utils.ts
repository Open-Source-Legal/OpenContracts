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
