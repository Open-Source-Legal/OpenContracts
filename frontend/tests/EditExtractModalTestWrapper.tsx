import React from "react";
import {
  MockedProvider,
  MockedResponse,
  MockLink,
} from "@apollo/client/testing";
import { InMemoryCache, ApolloLink, Observable } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { EditExtractModal } from "../src/components/widgets/modals/EditExtractModal";
import { relayStylePagination } from "@apollo/client/utilities";
import {
  authStatusVar,
  addingColumnToExtract,
  editingColumnForExtract,
} from "../src/graphql/cache";
import { mergeArrayByIdFieldPolicy } from "../src/graphql/cache";
import { REQUEST_GET_EXTRACT } from "../src/graphql/queries";
import { ExtractType } from "../src/types/graphql-api";

// Create minimal cache similar to DocumentKnowledgeBaseTestWrapper
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          extract: {
            // Simple read function that returns the extract by ID
            read(_, { args, toReference }) {
              return toReference({
                __typename: "ExtractType",
                id: args?.id,
              });
            },
          },
          extracts: relayStylePagination(),
        },
      },
      ExtractType: { keyFields: ["id"] },
      FieldsetType: { keyFields: ["id"] },
      ColumnType: { keyFields: ["id"] },
      DocumentType: { keyFields: ["id"] },
      DatacellType: { keyFields: ["id"] },
      ServerAnnotationType: {
        fields: {
          userFeedback: mergeArrayByIdFieldPolicy,
        },
      },
    },
  });

// Create wildcard link to respond to any REQUEST_GET_EXTRACT variables
const createWildcardLink = (mocks: ReadonlyArray<MockedResponse>) => {
  const mockLink = new MockLink(mocks);

  return new ApolloLink((operation) => {
    const isGetExtractQuery =
      operation.operationName === "GetExtract" ||
      operation.query === REQUEST_GET_EXTRACT;

    if (isGetExtractQuery) {
      // Find the mock that matches this extract ID
      const extractId = operation.variables.id;
      const matchingMock = mocks.find(
        (m) =>
          m.request.query === REQUEST_GET_EXTRACT &&
          m.request.variables?.id === extractId
      );

      if (matchingMock?.result) {
        console.log("[MOCK] wildcard GetExtract", operation.variables);
        return Observable.of(matchingMock.result as any);
      }
    }

    return mockLink.request(operation) as any;
  });
};

interface EditExtractModalTestWrapperProps {
  mocks: ReadonlyArray<MockedResponse>;
  open: boolean;
  ext: ExtractType | null;
  toggleModal: () => void;
}

export const EditExtractModalTestWrapper: React.FC<
  EditExtractModalTestWrapperProps
> = ({ mocks, open, ext, toggleModal }) => {
  // Mark authentication as done immediately for tests
  React.useEffect(() => {
    authStatusVar("ANONYMOUS");
  }, []);

  // Initialize reactive variables
  React.useEffect(() => {
    addingColumnToExtract(null);
    editingColumnForExtract(null);
  }, []);

  const link = createWildcardLink(mocks);

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider link={link} cache={createTestCache()} addTypename>
          <EditExtractModal open={open} ext={ext} toggleModal={toggleModal} />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
