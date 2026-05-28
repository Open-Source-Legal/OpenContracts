import React, { useState } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { CorpusDropdown } from "../src/components/widgets/selectors/CorpusDropdown";
import { GET_CORPUSES } from "../src/graphql/queries";
import { CorpusType } from "../src/types/graphql-api";

const corpusNodes = [
  {
    id: "corpus-1",
    slug: "test-corpus",
    icon: "folder",
    title: "Test Corpus",
    creator: { email: "user@example.com", slug: "user" },
    description: "A test corpus",
    descriptionPreview: "A test corpus",
    isPublic: true,
    isPersonal: false,
    is_selected: false,
    is_open: false,
    myPermissions: ["read"],
    documentCount: 5,
    parent: null,
    labelSet: null,
    categories: [],
  },
  {
    id: "corpus-2",
    slug: "another-corpus",
    icon: "book",
    title: "Another Corpus",
    creator: { email: "user@example.com", slug: "user" },
    description: "Another test corpus",
    descriptionPreview: "Another test corpus",
    isPublic: false,
    isPersonal: false,
    is_selected: false,
    is_open: false,
    myPermissions: ["read"],
    documentCount: 10,
    parent: null,
    labelSet: null,
    categories: [],
  },
];

const defaultMock: MockedResponse = {
  request: { query: GET_CORPUSES },
  variableMatcher: () => true,
  result: {
    data: {
      corpuses: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: "YXJyYXljb25uZWN0aW9uOjA=",
          endCursor: "YXJyYXljb25uZWN0aW9uOjA=",
        },
        edges: corpusNodes.map((node) => ({ node })),
      },
    },
  },
};

interface WrapperProps {
  placeholder?: string;
  clearable?: boolean;
  initialValue?: string;
  mocks?: MockedResponse[];
}

export const CorpusDropdownTestWrapper: React.FC<WrapperProps> = ({
  placeholder,
  clearable,
  initialValue,
  mocks,
}) => {
  const [selectedCorpus, setSelectedCorpus] = useState<CorpusType | null>(
    initialValue
      ? (corpusNodes.find(
          (c) => c.id === initialValue
        ) as unknown as CorpusType) ?? null
      : null
  );

  const handleChange = (corpus: CorpusType | null) => {
    setSelectedCorpus(corpus);
  };

  const allMocks = mocks ?? [
    defaultMock,
    { ...defaultMock },
    { ...defaultMock },
  ];

  return (
    <MockedProvider mocks={allMocks} addTypename={false}>
      <div style={{ padding: 24, maxWidth: 500 }}>
        <CorpusDropdown
          value={selectedCorpus?.id ?? null}
          onChange={handleChange}
          placeholder={placeholder}
          clearable={clearable}
        />
        <span
          data-testid="selected-corpus"
          style={{ position: "absolute", left: -9999 }}
        >
          {selectedCorpus?.id ?? ""}
        </span>
      </div>
    </MockedProvider>
  );
};

export { corpusNodes };
