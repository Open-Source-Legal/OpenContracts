import React, { useState } from "react";
import { Form, Grid } from "semantic-ui-react";
import { IconButton } from "@os-legal/ui";
import { motion, AnimatePresence } from "framer-motion";
import { Trash2 } from "lucide-react";
import styled from "styled-components";

export interface FieldType {
  fieldName: string;
  fieldType: string;
  id: string; // Added for stable animations
}

interface ModelFieldBuilderProps {
  onFieldsChange: (fields: FieldType[]) => void;
  initialFields?: FieldType[];
}

const containerVariants = {
  hidden: {
    opacity: 0,
    transition: { staggerChildren: 0.05, staggerDirection: -1 },
  },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
    },
  },
};

const fieldVariants = {
  hidden: {
    opacity: 0,
    x: -20,
    transition: { type: "tween" },
  },
  visible: {
    opacity: 1,
    x: 0,
    transition: { type: "spring", stiffness: 300, damping: 25 },
  },
  exit: {
    opacity: 0,
    x: -20,
    transition: { duration: 0.2 },
  },
};

const FieldRow = styled(motion.div)`
  margin-bottom: 1rem;
  background: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
`;

const AddFieldButton = styled(motion.button)`
  background: #2185d0;
  color: white;
  border: none;
  border-radius: 20px;
  padding: 12px 24px;
  cursor: pointer;
  width: 100%;
  margin-top: 1rem;
`;

const DeleteButtonWrapper = styled(motion.div)`
  display: inline-flex;

  button {
    border-radius: 50%;
    width: 40px;
    height: 40px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;

    &:hover {
      transform: rotate(90deg);
    }
  }
`;

/**
 * Converts field definitions to a Pydantic model string representation
 * @param fields - Array of field definitions
 * @returns Pydantic model as a string
 */
const generatePydanticModel = (fields: FieldType[]): string => {
  if (fields.length === 0) return "";

  const fieldLines = fields
    .map((field) => `    ${field.fieldName}: ${field.fieldType}`)
    .join("\n");

  return `class CustomModel(BaseModel):\n${fieldLines}`;
};

/**
 * Component for building custom model fields with animations.
 */
export const ModelFieldBuilder: React.FC<ModelFieldBuilderProps> = ({
  onFieldsChange,
  initialFields = [],
}) => {
  const [fields, setFields] = useState<FieldType[]>(
    initialFields.map((f) => ({ ...f, id: Math.random().toString() }))
  );

  const addField = () => {
    const newField = {
      fieldName: "",
      fieldType: "str",
      id: Math.random().toString(),
    };
    setFields([...fields, newField]);
  };

  const removeField = (index: number) => {
    const newFields = [...fields];
    newFields.splice(index, 1);
    setFields(newFields);
    onFieldsChange(newFields);
  };

  const updateField = (
    index: number,
    key: "fieldName" | "fieldType",
    value: string
  ) => {
    const newFields = [...fields];
    newFields[index][key] = value;
    setFields(newFields);
    onFieldsChange(newFields);
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      exit="hidden"
    >
      <Form>
        <AnimatePresence>
          {fields.map((field, index) => (
            <FieldRow key={field.id} variants={fieldVariants} layout>
              <Grid>
                <Grid.Row verticalAlign="middle">
                  <Grid.Column width={6}>
                    <Form.Input
                      placeholder="Field Name"
                      value={field.fieldName}
                      onChange={(e, { value }) =>
                        updateField(index, "fieldName", value)
                      }
                      required
                      fluid
                      label="Field Name"
                    />
                  </Grid.Column>
                  <Grid.Column width={6}>
                    <Form.Select
                      placeholder="Field Type"
                      value={field.fieldType}
                      options={[
                        { key: "int", text: "Integer", value: "int" },
                        { key: "float", text: "Float", value: "float" },
                        { key: "str", text: "String", value: "str" },
                        { key: "bool", text: "Boolean", value: "bool" },
                      ]}
                      onChange={(e, data) =>
                        updateField(index, "fieldType", data.value as string)
                      }
                      required
                      fluid
                      label="Field Type"
                    />
                  </Grid.Column>
                  <Grid.Column width={4} textAlign="center">
                    <DeleteButtonWrapper
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <IconButton
                        variant="danger"
                        onClick={() => removeField(index)}
                        aria-label="Delete field"
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </DeleteButtonWrapper>
                  </Grid.Column>
                </Grid.Row>
              </Grid>
            </FieldRow>
          ))}
        </AnimatePresence>

        <AddFieldButton
          onClick={addField}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          Add Field
        </AddFieldButton>
      </Form>
    </motion.div>
  );
};
