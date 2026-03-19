import React from "react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { ExtractCellFormatter } from "../src/components/extracts/datagrid/ExtractCellFormatter";
import { CellStatus } from "../src/types/extract-grid";

interface WrapperProps {
  value: any;
  cellStatus: CellStatus | null;
  isExtractComplete: boolean;
  readOnly?: boolean;
}

export const ExtractCellFormatterTestWrapper: React.FC<WrapperProps> = ({
  value,
  cellStatus,
  isExtractComplete,
  readOnly = false,
}) => (
  <MockedProvider mocks={[]} addTypename={false}>
    <MemoryRouter>
      <div style={{ width: "300px", height: "60px", position: "relative" }}>
        <ExtractCellFormatter
          value={value}
          cellStatus={cellStatus}
          cellId="test-cell-1"
          onApprove={() => {}}
          onReject={() => {}}
          onEdit={() => {}}
          readOnly={readOnly}
          isExtractComplete={isExtractComplete}
          schema={{ type: "string" }}
          extractIsList={false}
          row={{ col1: value }}
          column={{ key: "col1", name: "Column 1" }}
        />
      </div>
    </MemoryRouter>
  </MockedProvider>
);
