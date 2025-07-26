import React, { useEffect, type ReactNode } from "react";
import {
  MockedProvider,
  MockLink,
  type MockedResponse,
} from "@apollo/client/testing";
import { InMemoryCache, ApolloLink, Observable } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { mergeArrayByIdFieldPolicy } from "../src/graphql/cache"; // Assuming this is exported correctly
import { Provider } from "jotai"; // Import Jotai Provider
import { useAtom } from "jotai";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { PermissionTypes } from "../src/components/types";
import { LabelType } from "../src/components/annotator/types/enums";
import { OperationDefinitionNode } from "graphql";
import "../src/assets/styles/semantic.css"; // ADDED: Global Semantic UI styles

import DocumentKnowledgeBase from "../src/components/knowledge_base/document/DocumentKnowledgeBase";
import { authStatusVar, authToken, userObj } from "../src/graphql/cache";
import { MemoryRouter } from "react-router-dom";

// --- Minimal Test Cache Definition (copied from previous step) ---
// Create a minimal cache configuration for testing based on the real cache.
// This includes essential type policies for annotations but avoids problematic
// read functions that rely on external reactive variables.
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          // Use simple pagination for annotations in tests
          annotations: relayStylePagination(),
          // Include other paginated fields if needed by the component, using simple pagination
          userFeedback: relayStylePagination(),
          pageAnnotations: { keyArgs: false, merge: true }, // Simplest merge strategy
          documents: relayStylePagination(),
          corpuses: relayStylePagination(),
          userexports: relayStylePagination(),
          labelsets: relayStylePagination(),
          annotationLabels: relayStylePagination(),
          relationshipLabels: relayStylePagination(),
          extracts: relayStylePagination(),
          columns: relayStylePagination(),
        },
      },
      // Define keyFields for core types, but NO read functions
      DocumentType: {
        keyFields: ["id"],
      },
      CorpusType: {
        keyFields: ["id"],
      },
      LabelSetType: {
        keyFields: ["id"],
      },
      AnnotationType: {
        // Assuming AnnotationType is the primary type for annotations
        keyFields: ["id"],
      },
      ServerAnnotationType: {
        // Include if used distinctly
        keyFields: ["id"],
        fields: {
          // Keep simple merge policies if necessary
          userFeedback: mergeArrayByIdFieldPolicy,
        },
      },
      UserFeedbackType: {
        keyFields: ["id"],
      },
      DatacellType: {
        keyFields: ["id"],
      },
      PageAwareAnnotationType: {
        fields: {
          pageAnnotations: { keyArgs: false, merge: true },
        },
      },
    },
  });
// --- End Cache Definition ---

export const CONVERSATIONS_MOCK = {};

interface WrapperProps {
  mocks: ReadonlyArray<MockedResponse>;
  documentId: string;
  corpusId: string;
  readOnly?: boolean;
}

// Create a diagnostic component to monitor atom state
const CorpusStateDebugger = () => {
  const [corpusState] = useAtom(corpusStateAtom);

  // Log whenever the atom state changes
  useEffect(() => {
    console.log("[CorpusStateDebugger] Current atom state:", corpusState);
  }, [corpusState]);

  return null; // Render nothing
};

const conversationsMockData = {
  conversations: {
    edges: [
      {
        node: {
          id: "Q29udmVyc2F0aW9uVHlwZToz",
          title: "Transfer Taxes in Document Analysis",
          createdAt: "2025-05-19T05:23:56.913169+00:00",
          updatedAt: "2025-05-19T05:23:58.482189+00:00",
          creator: {
            id: "VXNlclR5cGU6Mw==",
            email: "scrudato@umich.edu",
            __typename: "UserType",
          },
          chatMessages: {
            totalCount: 2,
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
              __typename: "PageInfo",
            },
            __typename: "MessageTypeConnection",
          },
          isPublic: false,
          myPermissions: [],
          __typename: "ConversationType",
        },
        __typename: "ConversationTypeEdge",
      },
      {
        node: {
          id: "Q29udmVyc2F0aW9uVHlwZToy",
          title: "Transfer Taxes in Document Analysis",
          createdAt: "2025-05-19T05:17:30.973110+00:00",
          updatedAt: "2025-05-19T05:17:32.044191+00:00",
          creator: {
            id: "VXNlclR5cGU6Mw==",
            email: "scrudato@umich.edu",
            __typename: "UserType",
          },
          chatMessages: {
            totalCount: 2,
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
              __typename: "PageInfo",
            },
            __typename: "MessageTypeConnection",
          },
          isPublic: false,
          myPermissions: [],
          __typename: "ConversationType",
        },
        __typename: "ConversationTypeEdge",
      },
      {
        node: {
          id: "Q29udmVyc2F0aW9uVHlwZTox",
          title: "Tax Transfers Document Summary",
          createdAt: "2025-05-19T04:33:00.003664+00:00",
          updatedAt: "2025-05-19T04:33:02.400566+00:00",
          creator: {
            id: "VXNlclR5cGU6Mw==",
            email: "scrudato@umich.edu",
            __typename: "UserType",
          },
          chatMessages: {
            totalCount: 2,
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
              __typename: "PageInfo",
            },
            __typename: "MessageTypeConnection",
          },
          isPublic: false,
          myPermissions: [],
          __typename: "ConversationType",
        },
        __typename: "ConversationTypeEdge",
      },
    ],
    pageInfo: {
      hasNextPage: false,
      hasPreviousPage: false,
      startCursor: "YXJyYXljb25uZWN0aW9uOjA=",
      endCursor: "YXJyYXljb25uZWN0aW9uOjI=",
      __typename: "PageInfo",
    },
    __typename: "ConversationTypeConnection",
  },
};

/* ------------------------------------------------------------------ */
/* Mock payload returned by GET_CHAT_MESSAGES                          */
/* ------------------------------------------------------------------ */
const chatMessagesMockData = {
  chatMessages: [
    {
      id: "TWVzc2FnZVR5cGU6NQ==",
      msgType: "HUMAN",
      content: "What does this document say about Transfer Taxes?",
      data: {},
      __typename: "MessageType",
    },
    {
      id: "TWVzc2FnZVR5cGU6Ng==",
      msgType: "LLM",
      content:
        "The document specifies that Transfer Taxes, which include transfer, sales, value added, stamp duty, and similar taxes, are handled as follows:\n\n- **U.S. Government Taxes**: These are to be borne by ETON.\n- **Ex-U.S. Government Taxes**: These are to be borne by Aucta.",
      data: {
        sources: [
          {
            json: {
              "11": {
                bounds: {
                  top: 168.97299999999996,
                  left: 50.05,
                  right: 131.481,
                  bottom: 176.13099999999997,
                },
                rawText: "10. TRANSFER TAXES",
                tokensJsons: [
                  {
                    pageIndex: 11,
                    tokenIndex: 216,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 217,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 218,
                  },
                ],
              },
            },
            page: 11,
            label: "section_header",
            rawText: "10. TRANSFER TAXES",
            label_id: 43,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 149,
          },
          {
            json: {
              "11": {
                bounds: {
                  top: 179.07299999999998,
                  left: 50.05,
                  right: 544.95,
                  bottom: 207.02200000000005,
                },
                rawText:
                  "All transfer, sales, value added, stamp duty and similar Taxes (' Transfer Taxes ') payable to the U.S. government in connection with the transaction contemplated hereby will be borne by ETON and all Transfer Taxes payable to an ex-U.S. government in connection with the transaction contemplated hereby will be borne by Aucta.",
                tokensJsons: [
                  {
                    pageIndex: 11,
                    tokenIndex: 219,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 220,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 221,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 222,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 223,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 224,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 225,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 226,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 227,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 228,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 229,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 230,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 231,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 232,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 233,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 234,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 235,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 236,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 237,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 238,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 239,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 240,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 241,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 242,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 243,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 244,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 245,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 246,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 247,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 248,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 249,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 250,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 251,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 252,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 253,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 254,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 255,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 256,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 257,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 258,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 259,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 260,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 261,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 262,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 263,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 264,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 265,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 266,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 267,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 268,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 269,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 270,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 271,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 272,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 273,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 274,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 275,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 276,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 277,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 278,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 279,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 280,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 281,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 282,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 283,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 284,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 285,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 286,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 287,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 288,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 289,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 290,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 291,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 292,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 293,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 294,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 295,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 296,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 297,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 298,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 299,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 300,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 301,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 302,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 303,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 304,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 305,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 306,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 307,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 308,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 309,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 310,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 311,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 312,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 313,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 314,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 315,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 316,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 317,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 318,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 319,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 320,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 321,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 322,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 323,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 324,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 325,
                  },
                  {
                    pageIndex: 11,
                    tokenIndex: 326,
                  },
                ],
              },
            },
            page: 11,
            label: "text",
            rawText:
              "All transfer, sales, value added, stamp duty and similar Taxes (' Transfer Taxes ') payable to the U.S. government in connection with the transaction contemplated hereby will be borne by ETON and all Transfer Taxes payable to an ex-U.S. government in connection with the transaction contemplated hereby will be borne by Aucta.",
            label_id: 42,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 150,
          },
          {
            json: {
              "4": {
                bounds: {
                  top: 99.53599999999994,
                  left: 80.35,
                  right: 412.388,
                  bottom: 106.69399999999996,
                },
                rawText:
                  "1.40 ' Transfer Taxes ' shall have the meaning ascribed to this term in Section 10 of this Agreement.",
                tokensJsons: [
                  {
                    pageIndex: 4,
                    tokenIndex: 72,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 73,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 74,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 75,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 76,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 77,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 78,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 79,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 80,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 81,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 82,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 83,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 84,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 85,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 86,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 87,
                  },
                  {
                    pageIndex: 4,
                    tokenIndex: 88,
                  },
                ],
              },
            },
            page: 4,
            label: "list_item",
            rawText:
              "1.40 ' Transfer Taxes ' shall have the meaning ascribed to this term in Section 10 of this Agreement.",
            label_id: 44,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 64,
          },
          {
            json: {
              "3": {
                bounds: {
                  top: 193.59199999999998,
                  left: 50.05,
                  right: 544.95,
                  bottom: 261.942,
                },
                rawText:
                  "1.35 ' Taxes ' means taxes, duties, fees, premiums, assessments, imposts, levies and other charges of any kind whatsoever imposed by any Governmental Entity, including all interest, penalties, fines, additions to tax or other additional amounts imposed by any Governmental Entity in respect thereof, and including those levied on, or measured by, or referred to as, income, gross receipts, profits, capital, transfer, land transfer, sales, goods and services, harmonized sales, use, value-added, excise, stamp, withholding, business, franchising, property, development, occupancy, employer health, payroll, employment, health, social services, education and social security taxes, all surtaxes, all customs duties and import and export taxes, countervail and anti-dumping, all license, franchise and registration fees and all employment insurance, health insurance and government pension plan premiums or contributions.",
                tokensJsons: [
                  {
                    pageIndex: 3,
                    tokenIndex: 205,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 206,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 207,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 208,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 209,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 210,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 211,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 212,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 213,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 214,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 215,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 216,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 217,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 218,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 219,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 220,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 221,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 222,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 223,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 224,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 225,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 226,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 227,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 228,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 229,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 230,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 231,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 232,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 233,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 234,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 235,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 236,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 237,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 238,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 239,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 240,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 241,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 242,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 243,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 244,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 245,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 246,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 247,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 248,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 249,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 250,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 251,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 252,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 253,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 254,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 255,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 256,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 257,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 258,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 259,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 260,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 261,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 262,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 263,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 264,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 265,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 266,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 267,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 268,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 269,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 270,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 271,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 272,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 273,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 274,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 275,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 276,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 277,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 278,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 279,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 280,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 281,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 282,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 283,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 284,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 285,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 286,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 287,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 288,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 289,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 290,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 291,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 292,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 293,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 294,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 295,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 296,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 297,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 298,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 299,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 300,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 301,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 302,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 303,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 304,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 305,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 306,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 307,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 308,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 309,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 310,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 311,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 312,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 313,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 314,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 315,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 316,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 317,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 318,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 319,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 320,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 321,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 322,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 323,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 324,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 325,
                  },
                  {
                    pageIndex: 3,
                    tokenIndex: 326,
                  },
                ],
              },
            },
            page: 3,
            label: "list_item",
            rawText:
              "1.35 ' Taxes ' means taxes, duties, fees, premiums, assessments, imposts, levies and other charges of any kind whatsoever imposed by any Governmental Entity, including all interest, penalties, fines, additions to tax or other additional amounts imposed by any Governmental Entity in respect thereof, and including those levied on, or measured by, or referred to as, income, gross receipts, profits, capital, transfer, land transfer, sales, goods and services, harmonized sales, use, value-added, excise, stamp, withholding, business, franchising, property, development, occupancy, employer health, payroll, employment, health, social services, education and social security taxes, all surtaxes, all customs duties and import and export taxes, countervail and anti-dumping, all license, franchise and registration fees and all employment insurance, health insurance and government pension plan premiums or contributions.",
            label_id: 44,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 56,
          },
          {
            json: {
              "8": {
                bounds: {
                  top: 57.24199999999996,
                  left: 50.05,
                  right: 544.95,
                  bottom: 114.86000000000001,
                },
                rawText:
                  "6.6 Taxes. Each Party shall be responsible for and shall pay all Taxes payable on any income earned or received by it during the Term. Where required by law, ETON shall have the right to withhold applicable Taxes from any payments to be made hereunder by ETON to Aucta. Any Tax, duty or other levy paid or required to be withheld by ETON on account of any payments payable to Aucta under this Agreement shall be deducted from the amount of payments due to Aucta. ETON shall secure and promptly send to Aucta proof of such Taxes, duties or other levies withheld and paid by ETON for the benefit of Aucta. Each Party agrees to cooperate with the other Party in claiming exemptions from such deductions or withholdings under any agreement or treaty from time to time in effect.",
                tokensJsons: [
                  {
                    pageIndex: 8,
                    tokenIndex: 1,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 2,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 3,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 4,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 5,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 6,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 7,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 8,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 9,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 10,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 11,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 12,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 13,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 14,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 15,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 16,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 17,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 18,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 19,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 20,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 21,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 22,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 23,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 24,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 25,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 26,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 27,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 28,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 29,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 30,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 31,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 32,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 33,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 34,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 35,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 36,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 37,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 38,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 39,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 40,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 41,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 42,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 43,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 44,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 45,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 46,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 47,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 48,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 49,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 50,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 51,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 52,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 53,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 54,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 55,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 56,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 57,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 58,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 59,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 60,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 61,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 62,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 63,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 64,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 65,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 66,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 67,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 68,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 69,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 70,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 71,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 72,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 73,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 74,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 75,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 76,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 77,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 78,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 79,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 80,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 81,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 82,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 83,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 84,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 85,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 86,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 87,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 88,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 89,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 90,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 91,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 92,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 93,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 94,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 95,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 96,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 97,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 98,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 99,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 100,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 101,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 102,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 103,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 104,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 105,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 106,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 107,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 108,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 109,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 110,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 111,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 112,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 113,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 114,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 115,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 116,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 117,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 118,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 119,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 120,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 121,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 122,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 123,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 124,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 125,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 126,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 127,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 128,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 129,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 130,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 131,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 132,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 133,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 134,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 135,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 136,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 137,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 138,
                  },
                  {
                    pageIndex: 8,
                    tokenIndex: 139,
                  },
                ],
              },
            },
            page: 8,
            label: "text",
            rawText:
              "6.6 Taxes. Each Party shall be responsible for and shall pay all Taxes payable on any income earned or received by it during the Term. Where required by law, ETON shall have the right to withhold applicable Taxes from any payments to be made hereunder by ETON to Aucta. Any Tax, duty or other levy paid or required to be withheld by ETON on account of any payments payable to Aucta under this Agreement shall be deducted from the amount of payments due to Aucta. ETON shall secure and promptly send to Aucta proof of such Taxes, duties or other levies withheld and paid by ETON for the benefit of Aucta. Each Party agrees to cooperate with the other Party in claiming exemptions from such deductions or withholdings under any agreement or treaty from time to time in effect.",
            label_id: 42,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 121,
          },
          {
            json: {
              "20": {
                bounds: {
                  top: 158.24199999999996,
                  left: 50.05,
                  right: 544.95,
                  bottom: 215.86,
                },
                rawText:
                  "15.8 Assignment. The terms and provisions hereof shall inure to the benefit of, and be binding upon the Parties and their respective successors and permitted assigns. The Parties shall not assign, encumber or otherwise transfer this Agreement or any part of it to any Third Party, without the prior written consent of the other Party. Notwithstanding the foregoing, each Party may assign the rights and obligations under this Agreement in whole, without consent of the other Party, to a Third Party or Affiliate in connection with the transfer or sale of all or substantially all of its business or in the event of a merger, consolidation or change in control provided that the assignee assumes in writing and becomes directly obligated to the other Party to perform all of the obligations of assignor under this Agreement.",
                tokensJsons: [
                  {
                    pageIndex: 20,
                    tokenIndex: 174,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 175,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 176,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 177,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 178,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 179,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 180,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 181,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 182,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 183,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 184,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 185,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 186,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 187,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 188,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 189,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 190,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 191,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 192,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 193,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 194,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 195,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 196,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 197,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 198,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 199,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 200,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 201,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 202,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 203,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 204,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 205,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 206,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 207,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 208,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 209,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 210,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 211,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 212,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 213,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 214,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 215,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 216,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 217,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 218,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 219,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 220,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 221,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 222,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 223,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 224,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 225,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 226,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 227,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 228,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 229,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 230,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 231,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 232,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 233,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 234,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 235,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 236,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 237,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 238,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 239,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 240,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 241,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 242,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 243,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 244,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 245,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 246,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 247,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 248,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 249,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 250,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 251,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 252,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 253,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 254,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 255,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 256,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 257,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 258,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 259,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 260,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 261,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 262,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 263,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 264,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 265,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 266,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 267,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 268,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 269,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 270,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 271,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 272,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 273,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 274,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 275,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 276,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 277,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 278,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 279,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 280,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 281,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 282,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 283,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 284,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 285,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 286,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 287,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 288,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 289,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 290,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 291,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 292,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 293,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 294,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 295,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 296,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 297,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 298,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 299,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 300,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 301,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 302,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 303,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 304,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 305,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 306,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 307,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 308,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 309,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 310,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 311,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 312,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 313,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 314,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 315,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 316,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 317,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 318,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 319,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 320,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 321,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 322,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 323,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 324,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 325,
                  },
                  {
                    pageIndex: 20,
                    tokenIndex: 326,
                  },
                ],
              },
            },
            page: 20,
            label: "list_item",
            rawText:
              "15.8 Assignment. The terms and provisions hereof shall inure to the benefit of, and be binding upon the Parties and their respective successors and permitted assigns. The Parties shall not assign, encumber or otherwise transfer this Agreement or any part of it to any Third Party, without the prior written consent of the other Party. Notwithstanding the foregoing, each Party may assign the rights and obligations under this Agreement in whole, without consent of the other Party, to a Third Party or Affiliate in connection with the transfer or sale of all or substantially all of its business or in the event of a merger, consolidation or change in control provided that the assignee assumes in writing and becomes directly obligated to the other Party to perform all of the obligations of assignor under this Agreement.",
            label_id: 44,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 253,
          },
          {
            json: {
              "2": {
                bounds: {
                  top: 204.95399999999995,
                  left: 50.05,
                  right: 544.95,
                  bottom: 324.43499999999995,
                },
                rawText:
                  "1.26 ' Net Sales ' means, with respect to each Product sold in the Territory, the aggregate gross sales amount invoiced by ETON or any sublicensee or other party authorized by ETON to wholesale or distribute the Products on an arms-length basis to Third Parties in the Territory (' Gross Sales '), less (as applicable) the following ETON expenses as accrued and adjusted for amounts actually taken, consistent with ETON'S standard accounting practices in accordance with GAAP: (a) amounts refunded or credited for returned, damaged, outdated, short-dated or defective goods, and bad debts, and (b) all of the following: (i) taxes, duties and other governmental charges related to the production, use or sale of the Products (including, including without limitation the brand manufacturer's tax imposed pursuant to the Patient Protection and Affordable Care Act (Pub. L. No. 111-148) as amended or replaced, but not including taxes assessed against the income derived from such sale)\u037e (ii) trade, quantity and cash discounts, allowances, retroactive price adjustments, credit incentive payments, chargebacks, patient support programs, and rebates (including governmental rebates or other price reductions provided, based on sales by ETON to any Governmental Entity or regulatory authority in respect of state or federal Medicare, Medicaid, government pricing or similar programs\u037e)\u037e and (iii) any costs incurred in connection with or arising out of compliance with any Risk Evaluation and Mitigation Strategies approved by the FDA and (iv) any expenses associated with serialization of the Products. Distribution of Licensed Products for clinical trials or as samples will not be deemed a 'Net Sale' under this definition.",
                tokensJsons: [
                  {
                    pageIndex: 2,
                    tokenIndex: 207,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 208,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 209,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 210,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 211,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 212,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 213,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 214,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 215,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 216,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 217,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 218,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 219,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 220,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 221,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 222,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 223,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 224,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 225,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 226,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 227,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 228,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 229,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 230,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 231,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 232,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 233,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 234,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 235,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 236,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 237,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 238,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 239,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 240,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 241,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 242,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 243,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 244,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 245,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 246,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 247,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 248,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 249,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 250,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 251,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 252,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 253,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 254,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 255,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 256,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 257,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 258,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 259,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 260,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 261,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 262,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 263,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 264,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 265,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 266,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 267,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 268,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 269,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 270,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 271,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 272,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 273,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 274,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 275,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 276,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 277,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 278,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 279,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 280,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 281,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 282,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 283,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 284,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 285,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 286,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 287,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 288,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 289,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 290,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 291,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 292,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 293,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 294,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 295,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 296,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 297,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 298,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 299,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 300,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 301,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 302,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 303,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 304,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 305,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 306,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 307,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 308,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 309,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 310,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 311,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 312,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 313,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 314,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 315,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 316,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 317,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 318,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 319,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 320,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 321,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 322,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 323,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 324,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 325,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 326,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 327,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 328,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 329,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 330,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 331,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 332,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 333,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 334,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 335,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 336,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 337,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 338,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 339,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 340,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 341,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 342,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 343,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 344,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 345,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 346,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 347,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 348,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 349,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 350,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 351,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 352,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 353,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 354,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 355,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 356,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 357,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 358,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 359,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 360,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 361,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 362,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 363,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 364,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 365,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 366,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 367,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 368,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 369,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 370,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 371,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 372,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 373,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 374,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 375,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 376,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 377,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 378,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 379,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 380,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 381,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 382,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 383,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 384,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 385,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 386,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 387,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 388,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 389,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 390,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 391,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 392,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 393,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 394,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 395,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 396,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 397,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 398,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 399,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 400,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 401,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 402,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 403,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 404,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 405,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 406,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 407,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 408,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 409,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 410,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 411,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 412,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 413,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 414,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 415,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 416,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 417,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 418,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 419,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 420,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 421,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 422,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 423,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 424,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 425,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 426,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 427,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 428,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 429,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 430,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 431,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 432,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 433,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 434,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 435,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 436,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 437,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 438,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 439,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 440,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 441,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 442,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 443,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 444,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 445,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 446,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 447,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 448,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 449,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 450,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 451,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 452,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 453,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 454,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 455,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 456,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 457,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 458,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 459,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 460,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 461,
                  },
                  {
                    pageIndex: 2,
                    tokenIndex: 462,
                  },
                ],
              },
            },
            page: 2,
            label: "text",
            rawText:
              "1.26 ' Net Sales ' means, with respect to each Product sold in the Territory, the aggregate gross sales amount invoiced by ETON or any sublicensee or other party authorized by ETON to wholesale or distribute the Products on an arms-length basis to Third Parties in the Territory (' Gross Sales '), less (as applicable) the following ETON expenses as accrued and adjusted for amounts actually taken, consistent with ETON'S standard accounting practices in accordance with GAAP: (a) amounts refunded or credited for returned, damaged, outdated, short-dated or defective goods, and bad debts, and (b) all of the following: (i) taxes, duties and other governmental charges related to the production, use or sale of the Products (including, including without limitation the brand manufacturer's tax imposed pursuant to the Patient Protection and Affordable Care Act (Pub. L. No. 111-148) as amended or replaced, but not including taxes assessed against the income derived from such sale)\u037e (ii) trade, quantity and cash discounts, allowances, retroactive price adjustments, credit incentive payments, chargebacks, patient support programs, and rebates (including governmental rebates or other price reductions provided, based on sales by ETON to any Governmental Entity or regulatory authority in respect of state or federal Medicare, Medicaid, government pricing or similar programs\u037e)\u037e and (iii) any costs incurred in connection with or arising out of compliance with any Risk Evaluation and Mitigation Strategies approved by the FDA and (iv) any expenses associated with serialization of the Products. Distribution of Licensed Products for clinical trials or as samples will not be deemed a 'Net Sale' under this definition.",
            label_id: 42,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 44,
          },
          {
            json: {
              "7": {
                bounds: {
                  top: 107.74300000000005,
                  left: 61.412,
                  right: 544.95,
                  bottom: 135.06100000000004,
                },
                rawText:
                  "6.3.3 If the amount of royalty payment under Section 6.3.1 is less than the amount of royalty payment under Section 6.3.2, then ETON shall pay Aucta the difference between royalty payments in Sections 6.3.1 and 6.3.2 within sixty (60) days of the calendar year end, but in no event shall the difference paid be greater than the minimum amount in Section 6.3.2.",
                tokensJsons: [
                  {
                    pageIndex: 7,
                    tokenIndex: 67,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 68,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 69,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 70,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 71,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 72,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 73,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 74,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 75,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 76,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 77,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 78,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 79,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 80,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 81,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 82,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 83,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 84,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 85,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 86,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 87,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 88,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 89,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 90,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 91,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 92,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 93,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 94,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 95,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 96,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 97,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 98,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 99,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 100,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 101,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 102,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 103,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 104,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 105,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 106,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 107,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 108,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 109,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 110,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 111,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 112,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 113,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 114,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 115,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 116,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 117,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 118,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 119,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 120,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 121,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 122,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 123,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 124,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 125,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 126,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 127,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 128,
                  },
                ],
              },
            },
            page: 7,
            label: "text",
            rawText:
              "6.3.3 If the amount of royalty payment under Section 6.3.1 is less than the amount of royalty payment under Section 6.3.2, then ETON shall pay Aucta the difference between royalty payments in Sections 6.3.1 and 6.3.2 within sixty (60) days of the calendar year end, but in no event shall the difference paid be greater than the minimum amount in Section 6.3.2.",
            label_id: 42,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 111,
          },
          {
            json: {
              "7": {
                bounds: {
                  top: 87.543,
                  left: 122.013,
                  right: 420.594,
                  bottom: 94.66099999999994,
                },
                rawText:
                  "6.3.1 ETON shall pay to Aucta a royalty payment of [ * * * ] of Net Sales of the Products.",
                tokensJsons: [
                  {
                    pageIndex: 7,
                    tokenIndex: 40,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 41,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 42,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 43,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 44,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 45,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 46,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 47,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 48,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 49,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 50,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 51,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 52,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 53,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 54,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 55,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 56,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 57,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 58,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 59,
                  },
                  {
                    pageIndex: 7,
                    tokenIndex: 60,
                  },
                ],
              },
            },
            page: 7,
            label: "text",
            rawText:
              "6.3.1 ETON shall pay to Aucta a royalty payment of [ * * * ] of Net Sales of the Products.",
            label_id: 42,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 109,
          },
          {
            json: {
              "15": {
                bounds: {
                  top: 87.54200000000003,
                  left: 61.412,
                  right: 544.95,
                  bottom: 104.75999999999999,
                },
                rawText:
                  "12.2.1  it has the corporate power and authority to enter into this Agreement and to consummate the transactions contemplated hereby\u037e",
                tokensJsons: [
                  {
                    pageIndex: 15,
                    tokenIndex: 44,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 45,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 46,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 47,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 48,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 49,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 50,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 51,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 52,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 53,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 54,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 55,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 56,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 57,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 58,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 59,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 60,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 61,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 62,
                  },
                  {
                    pageIndex: 15,
                    tokenIndex: 63,
                  },
                ],
              },
            },
            page: 15,
            label: "text",
            rawText:
              "12.2.1  it has the corporate power and authority to enter into this Agreement and to consummate the transactions contemplated hereby\u037e",
            label_id: 42,
            bounding_box: {
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
            },
            annotation_id: 187,
          },
        ],
        message_id: 6,
      },
      __typename: "MessageType",
    },
  ],
};

// Build a link that handles addAnnotation mutations wildcard and falls back to the MockLink for other operations
const createWildcardLink = (mocks: ReadonlyArray<MockedResponse>) => {
  const defaultMockLink = new MockLink(mocks);
  return new ApolloLink((operation) => {
    // Look for the addAnnotation mutation by checking both operation name and query document
    const opDocument = operation.query.definitions.find(
      (def) =>
        def.kind === "OperationDefinition" && def.operation === "mutation"
    ) as OperationDefinitionNode | undefined;

    // Print operations being processed to help with debugging
    console.log(
      `[LINK DEBUG] Processing operation: ${operation.operationName}`
    );

    // Check if it's our mutation either by operationName or by query inspection
    const isAddAnnotationMutation =
      operation.operationName === "AddAnnotation" ||
      (opDocument?.selectionSet?.selections.some(
        (selection) =>
          selection.kind === "Field" && selection.name.value === "addAnnotation"
      ) ??
        false);

    if (isAddAnnotationMutation) {
      console.log(`[LINK HIT] Intercepted addAnnotation mutation`);
      const vars = operation.variables;
      console.log(
        "[MOCK HIT] REQUEST_ADD_ANNOTATION with variables:",
        JSON.stringify(vars, null, 2)
      );
      console.log("--- MUTATION MOCK EXECUTED ---");
      return Observable.of({
        data: {
          addAnnotation: {
            __typename: "AddAnnotationPayload",
            ok: true,
            annotation: {
              __typename: "AnnotationType",
              id: "new-annot-1",
              page: vars.page,
              rawText: (vars.rawText?.substring(0, 50) ?? "") + "...",
              bounds: {
                __typename: "BoundingBoxType",
                left: 100,
                top: 100,
                right: 200,
                bottom: 200,
                page: vars.page,
              },
              json: vars.json,
              isPublic: false,
              approved: false,
              rejected: false,
              structural: false,
              annotation_created: new Date().toISOString(),
              annotationType: vars.annotationType,
              myPermissions: [
                PermissionTypes.CAN_UPDATE,
                PermissionTypes.CAN_READ,
              ],
              annotationLabel: {
                __typename: "AnnotationLabelType",
                id: vars.annotationLabelId,
                icon: null,
                description: "A person entity",
                color: "#FF0000",
                text: "Person",
                labelType: LabelType.TokenLabel,
              },
              sourceNodeInRelationships: {
                __typename: "RelationshipTypeConnection",
                edges: [],
              },
              creator: {
                __typename: "UserType",
                id: "user-1",
                email: "test@test.com",
              },
            },
          },
        },
      });
    }

    /* ✅  wildcard for GetConversations -------------------------------- */
    if (operation.operationName === "GetConversations") {
      console.log("[MOCK HIT] GetConversations – wildcard match");
      return Observable.of({ data: conversationsMockData });
    }

    /* ✅  wildcard for GetChatMessages --------------------------------- */
    if (operation.operationName === "GetChatMessages") {
      console.log("[MOCK HIT] GetChatMessages – wildcard match");
      return Observable.of({ data: chatMessagesMockData });
    }

    // Delegate other operations to the default MockLink
    return defaultMockLink.request(operation) as any;
  });
};

export const DocumentKnowledgeBaseTestWrapper: React.FC<WrapperProps> = ({
  mocks,
  documentId,
  corpusId,
  readOnly = false,
}) => {
  // Create a link that handles wildcard mutation and other mocks
  const link = createWildcardLink(mocks);

  // Set up authentication for tests - BEFORE any components mount
  // This ensures ChatTray has auth token available on first render
  authToken("test-auth-token");
  userObj({
    id: "test-user",
    email: "test@example.com",
    username: "testuser",
  });

  // Mark auth as ready (anonymous) for tests
  useEffect(() => {
    authStatusVar("ANONYMOUS");
  }, []);
  return (
    <MemoryRouter
      initialEntries={[`/corpus/${corpusId}/document/${documentId}`]}
    >
      <Provider>
        <CorpusStateDebugger />
        <MockedProvider
          link={link}
          cache={createTestCache()}
          addTypename
          defaultOptions={{
            watchQuery: { errorPolicy: "all" },
            query: { errorPolicy: "all" },
            mutate: { errorPolicy: "all" },
          }}
        >
          <DocumentKnowledgeBase
            documentId={documentId}
            corpusId={corpusId}
            readOnly={readOnly}
          />
        </MockedProvider>
      </Provider>
    </MemoryRouter>
  );
};
