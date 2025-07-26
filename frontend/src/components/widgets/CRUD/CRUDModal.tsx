import React, { useEffect, useMemo, useState } from "react";
import { Button, Modal, Icon, Header, Loader, Dimmer } from "semantic-ui-react";
import _ from "lodash";
import { CRUDWidget } from "./CRUDWidget";
import { CRUDProps, LooseObject, PropertyWidgets } from "../../types";
import {
  HorizontallyCenteredDiv,
  VerticallyCenteredDiv,
} from "../../layout/Wrappers";

/**
 * Props for the ObjectCRUDModal component.
 */
export interface ObjectCRUDModalProps extends CRUDProps {
  open: boolean;
  oldInstance: Record<string, any>;
  propertyWidgets?: PropertyWidgets;
  onSubmit?: (instanceData: LooseObject) => void;
  onClose: () => void;
  /** When true the form is over-laid with a loader and inputs are disabled */
  loading?: boolean;
  children?: React.ReactNode;
}

/**
 * CRUDModal component provides a modal interface for creating, viewing, and editing instances.
 * It integrates the CRUDWidget for form handling and supports custom property widgets.
 *
 * @param {ObjectCRUDModalProps} props - The properties passed to the component.
 * @returns {JSX.Element} The rendered CRUD modal component.
 */
export function CRUDModal({
  open,
  mode,
  hasFile,
  fileField,
  fileLabel,
  fileIsImage,
  acceptedFileTypes,
  oldInstance,
  modelName,
  uiSchema,
  dataSchema,
  propertyWidgets,
  onSubmit,
  onClose,
  loading = false,
  children,
}: ObjectCRUDModalProps): JSX.Element {
  const [instanceObj, setInstanceObj] = useState<Record<string, any>>(
    oldInstance || {}
  );
  const [updatedFieldsObj, setUpdatedFields] = useState<Record<string, any>>({
    id: oldInstance?.id ?? -1,
  });

  const canWrite = mode !== "VIEW" && (mode === "CREATE" || mode === "EDIT");

  useEffect(() => {
    setInstanceObj(oldInstance || {});
    if (typeof oldInstance === "object" && oldInstance !== null) {
      setUpdatedFields({ id: oldInstance.id });
    }
  }, [oldInstance]);

  /**
   * Only keep truly changed fields in updatedFieldsObj
   */
  const handleModelChange = (updatedFields: LooseObject): void => {
    // Merge any new fields into instanceObj
    setInstanceObj((prevObj) => ({ ...prevObj, ...updatedFields }));

    // Figure out which fields have actually changed from oldInstance
    const changedFields = Object.entries(updatedFields).reduce(
      (acc, [key, value]) => {
        // If no difference, skip it
        if (_.isEqual(oldInstance[key], value)) return acc;
        return { ...acc, [key]: value };
      },
      {} as LooseObject
    );

    setUpdatedFields((prevFields) => ({
      ...prevFields,
      ...changedFields,
    }));
  };

  const appliedUISchema = useMemo(() => {
    return canWrite ? { ...uiSchema } : { ...uiSchema, "ui:readonly": true };
  }, [uiSchema, canWrite]);

  // Clone each widget so it can notify handleModelChange
  const listeningChildren: JSX.Element[] = useMemo(() => {
    if (!propertyWidgets) return [];
    return Object.keys(propertyWidgets)
      .map((key, index) => {
        const widget = propertyWidgets[key];
        if (React.isValidElement(widget)) {
          return React.cloneElement(widget, {
            [key]: instanceObj[key] || "",
            // Let the widget pass only changed fields to handleModelChange
            onChange: handleModelChange,
            key: index,
          });
        }
        return null;
      })
      .filter(Boolean) as JSX.Element[];
  }, [propertyWidgets, instanceObj, handleModelChange]);

  const descriptiveName = useMemo(
    () => modelName.charAt(0).toUpperCase() + modelName.slice(1),
    [modelName]
  );

  const headerText = useMemo(() => {
    switch (mode) {
      case "EDIT":
        return `Edit ${descriptiveName}: ${instanceObj.title ?? ""}`;
      case "VIEW":
        return `View ${descriptiveName}`;
      default:
        return `Create ${descriptiveName}`;
    }
  }, [mode, descriptiveName, instanceObj.title]);

  return (
    <Modal centered size="large" closeIcon open={open} onClose={onClose}>
      <Modal.Header>
        <HorizontallyCenteredDiv>
          <div style={{ marginTop: "1rem", textAlign: "left", width: "100%" }}>
            <Header as="h2">
              <Icon name="box" />
              <Header.Content>
                {headerText}
                <Header.Subheader>{`Values for: ${descriptiveName}`}</Header.Subheader>
              </Header.Content>
            </Header>
          </div>
        </HorizontallyCenteredDiv>
      </Modal.Header>
      <Modal.Content scrolling>
        {/* Overlay while the mutation is running */}
        {loading && (
          <Dimmer active inverted>
            <Loader>Saving&hellip;</Loader>
          </Dimmer>
        )}
        <CRUDWidget
          mode={mode}
          instance={instanceObj}
          modelName={modelName}
          uiSchema={appliedUISchema}
          dataSchema={dataSchema}
          showHeader={false}
          handleInstanceChange={handleModelChange}
          hasFile={hasFile}
          fileField={fileField}
          fileLabel={fileLabel}
          fileIsImage={fileIsImage}
          acceptedFileTypes={acceptedFileTypes}
        />
        <VerticallyCenteredDiv>{listeningChildren}</VerticallyCenteredDiv>
        {children}
      </Modal.Content>
      <Modal.Actions>
        <HorizontallyCenteredDiv>
          <Button basic color="grey" onClick={onClose} disabled={loading}>
            <Icon name="remove" /> Close
          </Button>
          {canWrite && onSubmit && !_.isEqual(oldInstance, instanceObj) && (
            <Button
              color="green"
              inverted
              loading={loading}
              disabled={loading}
              onClick={() => {
                onSubmit(mode === "EDIT" ? updatedFieldsObj : instanceObj);
              }}
            >
              <Icon name="checkmark" /> {mode === "EDIT" ? "Update" : "Create"}
            </Button>
          )}
        </HorizontallyCenteredDiv>
      </Modal.Actions>
    </Modal>
  );
}
