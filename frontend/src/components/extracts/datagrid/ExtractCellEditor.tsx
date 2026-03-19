import React, { useState } from "react";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
} from "@os-legal/ui";
import { JSONSchema7 } from "json-schema";
import JsonView from "@uiw/react-json-view";
import { darkTheme } from "@uiw/react-json-view/dark";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

interface ExtractCellEditorProps {
  row: any;
  column: any;
  onRowChange: (updatedRow: any, commitChanges?: boolean) => void;
  onClose: () => void;
  schema: JSONSchema7;
  extractIsList: boolean;
}

export const ExtractCellEditor: React.FC<ExtractCellEditorProps> = ({
  row,
  column,
  onRowChange,
  onClose,
  schema,
  extractIsList,
}) => {
  const initialValue = row[column.key];
  const [value, setValue] = useState(initialValue);
  const [isJsonModalOpen, setIsJsonModalOpen] = useState(false);

  /**
   * Handles input change events for string and number types.
   * @param event - The input change event.
   */
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setValue(event.target.value);
  };

  /**
   * Handles checkbox change events for boolean types.
   * @param event - The checkbox change event.
   */
  const handleCheckboxChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setValue(event.target.checked);
  };

  const handleJsonChange = (updatedValue: any) => {
    setValue(updatedValue);
  };

  const handleCommit = () => {
    onRowChange({ ...row, [column.key]: value }, true);
    onClose();
  };

  const renderJsonEditor = () => (
    <Modal open={isJsonModalOpen} onClose={() => setIsJsonModalOpen(false)}>
      <ModalHeader>Edit {column.name}</ModalHeader>
      <ModalBody
        style={{
          maxHeight: "70vh",
          overflow: "auto",
        }}
      >
        <JsonView
          src={value}
          theme={{
            ...darkTheme,
            backgroundColor: "#0f172a",
            fontSize: "14px",
            borderRadius: "8px",
          }}
          displayDataTypes={true}
          displayObjectSize={true}
          enableClipboard={true}
          onEdit={(edit: any) => {
            handleJsonChange(edit.updated_src);
          }}
          indentWidth={4}
          collapsed={false}
        />
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={() => setIsJsonModalOpen(false)}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleCommit}>
          Save
        </Button>
      </ModalFooter>
    </Modal>
  );

  const renderPrimitiveEditor = () => {
    const { type } = schema;

    switch (type) {
      case "string":
        return (
          <Input
            fullWidth
            value={value}
            onChange={handleInputChange}
            autoFocus
          />
        );

      case "number":
        return (
          <Input
            fullWidth
            type="number"
            value={value}
            onChange={handleInputChange}
            autoFocus
          />
        );

      case "boolean":
        return (
          <input
            type="checkbox"
            checked={value}
            onChange={handleCheckboxChange}
            autoFocus
          />
        );

      default:
        return (
          <Input
            fullWidth
            value={String(value)}
            onChange={handleInputChange}
            autoFocus
          />
        );
    }
  };

  if (schema.type === "object" || extractIsList) {
    return (
      <>
        <Button variant="secondary" onClick={() => setIsJsonModalOpen(true)}>
          Edit JSON
        </Button>
        {isJsonModalOpen && renderJsonEditor()}
      </>
    );
  }

  return (
    <>
      {renderPrimitiveEditor()}
      <div
        style={{
          marginTop: "1em",
          textAlign: "right",
          display: "flex",
          gap: "0.5rem",
          justifyContent: "flex-end",
        }}
      >
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleCommit}>
          Save
        </Button>
      </div>
    </>
  );
};
