import React, { useEffect, useMemo, useState } from "react";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { Box, X, Check } from "lucide-react";
import _ from "lodash";
import { CRUDWidget } from "./CRUDWidget";
import { LoadingOverlay } from "../../common/LoadingOverlay";
import { CRUDProps, LooseObject, PropertyWidgets } from "../../types";
import {
  HorizontallyCenteredDiv,
  VerticallyCenteredDiv,
} from "../../layout/Wrappers";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import styled from "styled-components";

const ValidationErrors = styled.div`
  color: var(--oc-color-error, ${OS_LEGAL_COLORS.danger});
  font-size: var(--oc-font-size-sm, 0.875rem);
  text-align: center;
  margin-bottom: var(--oc-spacing-sm, 0.5rem);
`;

/**
 * Props for the ObjectCRUDModal component.
 */
export interface ObjectCRUDModalProps<
  T extends Record<string, any> = Record<string, any>,
> extends CRUDProps {
  open: boolean;
  oldInstance: Record<string, any>;
  propertyWidgets?: PropertyWidgets;
  onSubmit?: (instanceData: LooseObject) => void;
  onClose: () => void;
  /** When true the form is over-laid with a loader and inputs are disabled */
  loading?: boolean;
  children?: React.ReactNode;
  /** Render prop for form fields. Receives current data, onChange, and disabled flag. */
  renderForm: (
    formData: T,
    onChange: (updates: Partial<T>) => void,
    disabled: boolean
  ) => React.ReactNode;
  /** Optional validation function. Returns an array of error messages, or empty array if valid. */
  validate?: (formData: T) => string[];
}

/**
 * CRUDModal component provides a modal interface for creating, viewing, and editing instances.
 * It integrates the CRUDWidget for form handling and supports custom property widgets.
 *
 * @param {ObjectCRUDModalProps} props - The properties passed to the component.
 * @returns {JSX.Element} The rendered CRUD modal component.
 */
export function CRUDModal<T extends Record<string, any> = Record<string, any>>({
  open,
  mode,
  hasFile,
  fileField,
  fileLabel,
  fileIsImage,
  acceptedFileTypes,
  oldInstance,
  modelName,
  propertyWidgets,
  onSubmit,
  onClose,
  loading = false,
  children,
  renderForm,
  validate,
}: ObjectCRUDModalProps<T>): JSX.Element {
  const [instanceObj, setInstanceObj] = useState<Record<string, any>>(
    oldInstance || {}
  );
  const [updatedFieldsObj, setUpdatedFields] = useState<Record<string, any>>({
    id: oldInstance?.id ?? -1,
  });

  const canWrite = mode !== "VIEW" && (mode === "CREATE" || mode === "EDIT");

  const validationErrors = useMemo(
    () => (validate ? validate(instanceObj as T) : []),
    [validate, instanceObj]
  );
  const isValid = validationErrors.length === 0;

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
    <Modal open={open} onClose={onClose} size="lg">
      <ModalHeader
        title={
          <HorizontallyCenteredDiv>
            <div
              style={{ marginTop: "1rem", textAlign: "left", width: "100%" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Box size={24} />
                <div>
                  <h2 style={{ margin: 0 }}>{headerText}</h2>
                  <div
                    style={{
                      fontSize: "0.875rem",
                      color: OS_LEGAL_COLORS.textSecondary,
                    }}
                  >{`Values for: ${descriptiveName}`}</div>
                </div>
              </div>
            </div>
          </HorizontallyCenteredDiv>
        }
        onClose={onClose}
      />
      <ModalBody style={{ position: "relative", overflow: "auto" }}>
        {/* Overlay while the mutation is running */}
        <LoadingOverlay active={loading} inverted content="Saving..." />
        <CRUDWidget<T>
          mode={mode}
          instance={instanceObj as T}
          modelName={modelName}
          showHeader={false}
          handleInstanceChange={handleModelChange as (inst: T) => void}
          hasFile={hasFile}
          fileField={fileField}
          fileLabel={fileLabel}
          fileIsImage={fileIsImage}
          acceptedFileTypes={acceptedFileTypes}
          renderForm={renderForm}
        />
        <VerticallyCenteredDiv>{listeningChildren}</VerticallyCenteredDiv>
        {children}
      </ModalBody>
      <ModalFooter>
        {canWrite &&
          validationErrors.length > 0 &&
          !_.isEqual(oldInstance, instanceObj) && (
            <ValidationErrors>
              {validationErrors.map((err, i) => (
                <div key={i}>{err}</div>
              ))}
            </ValidationErrors>
          )}
        <HorizontallyCenteredDiv>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={loading}
            leftIcon={<X size={16} />}
          >
            Close
          </Button>
          {canWrite && onSubmit && (
            <Button
              variant="primary"
              loading={loading}
              disabled={
                loading || !isValid || _.isEqual(oldInstance, instanceObj)
              }
              leftIcon={<Check size={16} />}
              onClick={() => {
                onSubmit(mode === "EDIT" ? updatedFieldsObj : instanceObj);
              }}
            >
              {mode === "EDIT" ? "Update" : "Create"}
            </Button>
          )}
        </HorizontallyCenteredDiv>
      </ModalFooter>
    </Modal>
  );
}
