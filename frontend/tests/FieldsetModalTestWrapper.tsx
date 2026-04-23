// Mock builders live in FieldsetModalMocks.ts — Playwright CT's babel
// plugin only accepts React components as exports from *TestWrapper files.
import React, { useState } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { FieldsetModal } from "../src/components/widgets/modals/FieldsetModal";
import { GET_REGISTERED_EXTRACT_TASKS } from "../src/graphql/queries";
import { FieldsetType } from "../src/types/graphql-api";
import { DEFAULT_EXTRACT_TASK_NAME } from "./FieldsetModalMocks";

const extractTasksMock: MockedResponse = {
  request: { query: GET_REGISTERED_EXTRACT_TASKS },
  result: {
    data: {
      registeredExtractTasks: {
        [DEFAULT_EXTRACT_TASK_NAME]:
          "Extract structured data using LLM queries",
      },
    },
  },
};

// One per test that opens CreateColumnModal (which refetches this query);
// MockedProvider consumes entries sequentially, so we duplicate rather than
// reuse. Extra entries cover strict-mode/double-mount re-renders.
const defaultTaskMocks: MockedResponse[] = Array.from({ length: 6 }, () => ({
  ...extractTasksMock,
}));

interface WrapperProps {
  startOpen?: boolean;
  mode?: "create" | "edit";
  existingFieldset?: FieldsetType | null;
  mocks?: MockedResponse[];
}

export const FieldsetModalTestWrapper: React.FC<WrapperProps> = ({
  startOpen = true,
  mode = "create",
  existingFieldset = null,
  mocks,
}) => {
  const [open, setOpen] = useState(startOpen);
  const [successPayload, setSuccessPayload] = useState<string>("");

  // Edit-mode callers pass supplemental mocks (e.g. REQUEST_GET_FIELDSET).
  // Always prepend the default task mocks so FieldsetModal's GET_REGISTERED_
  // EXTRACT_TASKS query resolves regardless of what the caller passes.
  const effectiveMocks = [...defaultTaskMocks, ...(mocks ?? [])];

  return (
    <MockedProvider mocks={effectiveMocks} addTypename={false}>
      <div style={{ padding: 24 }}>
        <button onClick={() => setOpen(true)} data-testid="open-fieldset-modal">
          Open Fieldset Modal
        </button>
        <FieldsetModal
          open={open}
          mode={mode}
          existingFieldset={existingFieldset}
          onClose={() => setOpen(false)}
          onSuccess={(fs) => {
            setSuccessPayload(JSON.stringify(fs));
            setOpen(false);
          }}
        />
        <span
          data-testid="success-payload"
          style={{ position: "absolute", left: -9999 }}
        >
          {successPayload}
        </span>
      </div>
    </MockedProvider>
  );
};
