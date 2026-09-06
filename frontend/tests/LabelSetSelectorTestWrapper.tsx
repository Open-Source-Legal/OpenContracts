import React, { useState } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { LabelSetSelector } from "../src/components/widgets/CRUD/LabelSetSelector";
import { LabelSetType } from "../src/types/graphql-api";
import { GET_LABELSETS } from "../src/graphql/queries";

const labelsetNodes = [
  {
    id: "ls-1",
    icon: "tags",
    title: "Contract Labels",
    description: "Labels for contract analysis",
    created: "2024-01-01T00:00:00Z",
    is_selected: false,
    is_open: false,
    isPublic: true,
    myPermissions: ["read"],
  },
  {
    id: "ls-2",
    icon: "file",
    title: "Financial Labels",
    description: "Labels for financial documents",
    created: "2024-01-02T00:00:00Z",
    is_selected: false,
    is_open: false,
    isPublic: true,
    myPermissions: ["read"],
  },
];

const defaultMock: MockedResponse = {
  request: { query: GET_LABELSETS },
  variableMatcher: () => true,
  result: {
    data: {
      labelsets: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: "YXJyYXljb25uZWN0aW9uOjA=",
          endCursor: "YXJyYXljb25uZWN0aW9uOjA=",
        },
        edges: labelsetNodes.map((node) => ({ node })),
      },
    },
  },
};

interface WrapperProps {
  labelSet?: LabelSetType;
  read_only?: boolean;
  mocks?: MockedResponse[];
}

export const LabelSetSelectorTestWrapper: React.FC<WrapperProps> = ({
  labelSet: initialLabelSet,
  read_only = false,
  mocks,
}) => {
  const [selectedLabelSet, setSelectedLabelSet] = useState<
    LabelSetType | undefined
  >(initialLabelSet);

  const handleChange = (values: any) => {
    if (values.labelSet === null) {
      setSelectedLabelSet(undefined);
    } else if (values.labelSetObj) {
      // Mirror CorpusModal: consumers need the selected object immediately so
      // the controlled dropdown reflects the user's choice.
      setSelectedLabelSet(values.labelSetObj);
    }
  };

  const allMocks = mocks ?? [
    defaultMock,
    { ...defaultMock },
    { ...defaultMock },
  ];

  return (
    <MockedProvider mocks={allMocks} addTypename={false}>
      <div style={{ padding: 24, maxWidth: 500 }}>
        <LabelSetSelector
          labelSet={selectedLabelSet}
          read_only={read_only}
          onChange={handleChange}
        />
        <span
          data-testid="selected-labelset"
          style={{ position: "absolute", left: -9999 }}
        >
          {selectedLabelSet?.id ?? ""}
        </span>
      </div>
    </MockedProvider>
  );
};

export { labelsetNodes };
