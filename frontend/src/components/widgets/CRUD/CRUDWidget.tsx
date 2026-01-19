import React, { useCallback, useMemo } from "react";
import { Header, Label, Grid } from "semantic-ui-react";
import styled from "styled-components";
import { Box } from "lucide-react";
import Form from "@rjsf/semantic-ui";
import validator from "@rjsf/validator-ajv8";
import {
  HorizontallyCenteredDiv,
  VerticallyCenteredDiv,
} from "../../layout/Wrappers";
import { FilePreviewAndUpload } from "../file-controls/FilePreviewAndUpload";
import { CRUDProps, LooseObject } from "../../types";

const RaisedSegment = styled.div`
  background: #fff;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-radius: 8px;
  padding: 1.5rem;
  margin: 1rem 0;
  box-shadow: 0 2px 4px 0 rgba(34, 36, 38, 0.12), 0 2px 5px rgba(0, 0, 0, 0.1);
  width: 100%;
`;

/**
 * Props for the CRUDWidget component.
 *
 * @template T - The type of the instance being managed.
 */
interface CRUDWidgetProps<T extends Record<string, any>> extends CRUDProps {
  instance: T | Partial<T>;
  showHeader: boolean;
  handleInstanceChange: (updatedInstance: T) => void;
}

/**
 * CRUDWidget component provides a form interface for creating, viewing, and editing instances.
 * It includes optional file upload functionality and responsive layout adjustments.
 *
 * @template T - The type of the instance being managed.
 * @param {CRUDWidgetProps<T>} props - The properties passed to the component.
 * @returns {JSX.Element} The rendered CRUD widget component.
 */
export const CRUDWidget = <T extends Record<string, any>>({
  mode,
  instance,
  modelName,
  hasFile,
  fileField,
  fileLabel,
  fileIsImage,
  acceptedFileTypes,
  uiSchema,
  dataSchema,
  showHeader,
  handleInstanceChange,
}: CRUDWidgetProps<T>): JSX.Element => {
  const canWrite = mode === "CREATE" || mode === "EDIT";

  /**
   * Cleans the form data by retaining only the properties defined in the data schema.
   *
   * @param {LooseObject} instanceData - The current instance data.
   * @param {LooseObject} schema - The data schema defining the properties.
   * @returns {Partial<T>} The cleaned form data.
   */
  const cleanFormData = useCallback(
    (instanceData: LooseObject, schema: LooseObject): Partial<T> => {
      return Object.keys(schema.properties).reduce((acc, key) => {
        if (key in instanceData) {
          acc[key as keyof T] = instanceData[key];
        }
        return acc;
      }, {} as Partial<T>);
    },
    []
  );

  /**
   * Handles changes in the form data and propagates them upwards.
   *
   * @param {Record<string, any>} param0 - The form data change event.
   */
  const handleChange = useCallback(
    ({ formData }: Record<string, any>) => {
      handleInstanceChange(formData as T);
    },
    [handleInstanceChange]
  );

  const descriptiveName = useMemo(
    () => modelName.charAt(0).toUpperCase() + modelName.slice(1),
    [modelName]
  );

  const headerText = useMemo(() => {
    switch (mode) {
      case "EDIT":
        return `Edit ${descriptiveName}: ${instance.title}`;
      case "VIEW":
        return `View ${descriptiveName}`;
      default:
        return `Create ${descriptiveName}`;
    }
  }, [mode, descriptiveName, instance.title]);

  const formData = useMemo(
    () => cleanFormData(instance as T, dataSchema),
    [instance, dataSchema, cleanFormData]
  );

  return (
    <div style={{ marginBottom: "1rem" }}>
      {showHeader && (
        <HorizontallyCenteredDiv>
          <div style={{ marginTop: "1rem", textAlign: "left", width: "100%" }}>
            <Header as="h2" textAlign="center">
              <Box
                size={32}
                style={{
                  maxWidth: "50px",
                  height: "auto",
                  margin: "0 auto",
                  marginBottom: "0.5rem",
                }}
                className="responsive-icon"
              />
              <Header.Content>
                {headerText}
                <Header.Subheader>{`Values for: ${descriptiveName}`}</Header.Subheader>
              </Header.Content>
            </Header>
          </div>
        </HorizontallyCenteredDiv>
      )}
      <HorizontallyCenteredDiv>
        <VerticallyCenteredDiv>
          <RaisedSegment>
            <Grid stackable>
              {hasFile && (
                <Grid.Row>
                  <Grid.Column width={16}>
                    <Label>{fileLabel}</Label>
                    <FilePreviewAndUpload
                      readOnly={!canWrite}
                      isImage={fileIsImage}
                      acceptedTypes={acceptedFileTypes}
                      disabled={!canWrite}
                      file={instance?.[fileField] || null}
                      onChange={({ data, filename }) =>
                        handleInstanceChange({
                          ...instance,
                          [fileField]: data,
                          filename,
                        } as T)
                      }
                    />
                  </Grid.Column>
                </Grid.Row>
              )}
              <Grid.Row>
                <Grid.Column width={16}>
                  <Form
                    schema={dataSchema}
                    uiSchema={uiSchema}
                    validator={validator}
                    onChange={handleChange}
                    formData={formData}
                    noHtml5Validate
                    liveValidate
                    showErrorList={false}
                    className="responsive-form"
                  >
                    <Grid columns={2} stackable>
                      <Grid.Row>
                        <Grid.Column>
                          <></>
                        </Grid.Column>
                        <Grid.Column>
                          <></>
                        </Grid.Column>
                      </Grid.Row>
                    </Grid>
                  </Form>
                </Grid.Column>
              </Grid.Row>
            </Grid>
          </RaisedSegment>
        </VerticallyCenteredDiv>
      </HorizontallyCenteredDiv>
    </div>
  );
};
