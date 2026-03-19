import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { gql } from "@apollo/client";
import { SelectDocumentsModal } from "../src/components/widgets/modals/SelectDocumentsModal";

const SEARCH_DOCUMENTS = gql`
  query SearchDocuments(
    $textSearch: String
    $hasLabelWithId: String
    $inCorpusWithId: String
    $annotateDocLabels: Boolean
    $includeMetadata: Boolean
    $cursor: String
    $limit: Int
  ) {
    documents(
      textSearch: $textSearch
      hasLabelWithId: $hasLabelWithId
      inCorpusWithId: $inCorpusWithId
      annotateDocLabels: $annotateDocLabels
      includeMetadata: $includeMetadata
      after: $cursor
      first: $limit
    ) {
      edges {
        node {
          id
          title
          description
          icon
          pdfFile
          txtExtractFile
          backendLock
          isPublic
          myPermissions
          isPublished
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
`;

const defaultMock: MockedResponse = {
  request: {
    query: SEARCH_DOCUMENTS,
  },
  variableMatcher: () => true,
  result: {
    data: {
      documents: {
        edges: [],
        pageInfo: {
          hasNextPage: false,
          endCursor: null,
        },
      },
    },
  },
};

interface WrapperProps {
  open?: boolean;
  mocks?: MockedResponse[];
  toggleModal?: () => void;
  onAddDocumentIds?: (ids: string[]) => void;
}

export const SelectDocumentsModalTestWrapper: React.FC<WrapperProps> = ({
  open = true,
  mocks = [defaultMock],
  toggleModal = () => {},
  onAddDocumentIds = () => {},
}) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <MemoryRouter>
      <SelectDocumentsModal
        open={open}
        filterDocIds={[]}
        toggleModal={toggleModal}
        onAddDocumentIds={onAddDocumentIds}
      />
    </MemoryRouter>
  </MockedProvider>
);
