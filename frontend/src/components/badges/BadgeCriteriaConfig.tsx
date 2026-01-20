import React, { useState, useEffect } from "react";
import { useQuery } from "@apollo/client";
import { Dropdown } from "semantic-ui-react";
import { Alert, FormField, Input } from "@os-legal/ui";
import {
  GET_BADGE_CRITERIA_TYPES,
  GetBadgeCriteriaTypesInput,
  GetBadgeCriteriaTypesOutput,
  CriteriaTypeDefinition,
  CriteriaField,
} from "../../graphql/queries";

interface BadgeCriteriaConfigProps {
  badgeType: "GLOBAL" | "CORPUS";
  criteriaConfig: any;
  onChange: (data: { config: any; isValid: boolean }) => void;
}

/**
 * Component for configuring badge auto-award criteria.
 *
 * This component:
 * - Fetches available criteria types from the registry
 * - Displays a dropdown to select criteria type
 * - Dynamically renders form fields based on selected type
 * - Validates inputs in real-time
 * - Passes validated config back to parent via onChange
 *
 * @param badgeType - Whether this is a GLOBAL or CORPUS badge
 * @param criteriaConfig - Current criteria configuration
 * @param onChange - Callback to pass config changes to parent
 */
export const BadgeCriteriaConfig: React.FC<BadgeCriteriaConfigProps> = ({
  badgeType,
  criteriaConfig,
  onChange,
}) => {
  const [selectedType, setSelectedType] = useState<string>(
    criteriaConfig?.type || ""
  );
  const [fieldValues, setFieldValues] = useState<Record<string, any>>(
    criteriaConfig || {}
  );
  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({});

  // Determine scope based on badge type
  const scope = badgeType === "GLOBAL" ? "global" : "corpus";

  // Fetch available criteria types
  const { loading, error, data } = useQuery<
    GetBadgeCriteriaTypesOutput,
    GetBadgeCriteriaTypesInput
  >(GET_BADGE_CRITERIA_TYPES, {
    variables: { scope },
  });

  const criteriaTypes: CriteriaTypeDefinition[] =
    data?.badgeCriteriaTypes || [];
  const currentType = criteriaTypes.find((ct) => ct.typeId === selectedType);

  /**
   * Validate a single field value against its definition
   */
  const validateField = (field: CriteriaField, value: any): string | null => {
    // Check required fields
    if (
      field.required &&
      (value === undefined || value === null || value === "")
    ) {
      return `${field.label} is required`;
    }

    // Skip validation for empty optional fields
    if (value === undefined || value === null || value === "") {
      return null;
    }

    // Type-specific validation
    if (field.fieldType === "number") {
      const numValue = Number(value);
      if (isNaN(numValue)) {
        return `${field.label} must be a valid number`;
      }
      if (field.minValue !== undefined && numValue < field.minValue) {
        return `${field.label} must be at least ${field.minValue}`;
      }
      if (field.maxValue !== undefined && numValue > field.maxValue) {
        return `${field.label} must be at most ${field.maxValue}`;
      }
    } else if (field.fieldType === "text") {
      if (typeof value !== "string") {
        return `${field.label} must be text`;
      }
      if (
        field.allowedValues &&
        field.allowedValues.length > 0 &&
        !field.allowedValues.includes(value)
      ) {
        return `${field.label} must be one of: ${field.allowedValues.join(
          ", "
        )}`;
      }
    } else if (field.fieldType === "boolean") {
      if (typeof value !== "boolean") {
        return `${field.label} must be true or false`;
      }
    }

    return null;
  };

  /**
   * Validate all fields and return whether config is valid
   */
  const validateAllFields = (): boolean => {
    if (!currentType) return false;

    const errors: Record<string, string> = {};
    let hasErrors = false;

    currentType.fields.forEach((field) => {
      const error = validateField(field, fieldValues[field.name]);
      if (error) {
        errors[field.name] = error;
        hasErrors = true;
      }
    });

    setValidationErrors(errors);
    return !hasErrors;
  };

  /**
   * Handle criteria type selection
   */
  const handleTypeChange = (value: string) => {
    setSelectedType(value);
    // Reset field values when type changes, keeping only 'type'
    setFieldValues({ type: value });
    setValidationErrors({});
  };

  /**
   * Handle individual field value changes
   */
  const handleFieldChange = (fieldName: string, value: any) => {
    setFieldValues((prev) => ({
      ...prev,
      [fieldName]: value,
    }));

    // Clear validation error for this field
    setValidationErrors((prev) => {
      const newErrors = { ...prev };
      delete newErrors[fieldName];
      return newErrors;
    });
  };

  /**
   * Notify parent of config changes
   */
  useEffect(() => {
    if (selectedType && currentType) {
      const isValid = validateAllFields();
      onChange({
        config: { type: selectedType, ...fieldValues },
        isValid,
      });
    } else {
      onChange({ config: null, isValid: false });
    }
  }, [selectedType, fieldValues]);

  // Show loading state
  if (loading) {
    return (
      <Alert variant="info" title="Loading Criteria Types">
        Fetching available auto-award criteria...
      </Alert>
    );
  }

  // Show error state
  if (error) {
    return (
      <Alert variant="error" title="Error Loading Criteria Types">
        {error.message}
      </Alert>
    );
  }

  // Filter to only implemented criteria types
  const implementedTypes = criteriaTypes.filter((ct) => ct.implemented);

  if (implementedTypes.length === 0) {
    return (
      <Alert variant="warning" title="No Criteria Types Available">
        There are no criteria types available for {badgeType.toLowerCase()}{" "}
        badges yet.
      </Alert>
    );
  }

  // Prepare dropdown options
  const typeOptions = implementedTypes.map((ct) => ({
    key: ct.typeId,
    text: ct.name,
    value: ct.typeId,
    description: ct.description,
  }));

  return (
    <div>
      <FormField label="Auto-Award Criteria Type" required>
        <Dropdown
          placeholder="Select criteria type"
          fluid
          selection
          search
          options={typeOptions}
          value={selectedType}
          onChange={(_, { value }) => handleTypeChange(value as string)}
        />
      </FormField>

      {currentType && (
        <>
          <Alert variant="info" title={currentType.name}>
            {currentType.description}
          </Alert>

          {currentType.fields.map((field) => (
            <FormField
              key={field.name}
              label={field.label}
              required={field.required}
              helperText={field.description}
              error={validationErrors[field.name]}
            >
              {field.fieldType === "number" && (
                <Input
                  type="number"
                  min={field.minValue}
                  max={field.maxValue}
                  value={fieldValues[field.name] ?? ""}
                  onChange={(e) =>
                    handleFieldChange(
                      field.name,
                      e.target.value === ""
                        ? undefined
                        : parseInt(e.target.value)
                    )
                  }
                  placeholder={`Enter ${field.label.toLowerCase()}`}
                  error={!!validationErrors[field.name]}
                />
              )}

              {field.fieldType === "text" && !field.allowedValues && (
                <Input
                  type="text"
                  value={fieldValues[field.name] ?? ""}
                  onChange={(e) =>
                    handleFieldChange(field.name, e.target.value)
                  }
                  placeholder={`Enter ${field.label.toLowerCase()}`}
                  error={!!validationErrors[field.name]}
                />
              )}

              {field.fieldType === "text" && field.allowedValues && (
                <Dropdown
                  fluid
                  selection
                  options={field.allowedValues.map((val) => ({
                    key: val,
                    text: val,
                    value: val,
                  }))}
                  value={fieldValues[field.name] ?? ""}
                  onChange={(_, { value }) =>
                    handleFieldChange(field.name, value as string)
                  }
                  placeholder={`Select ${field.label.toLowerCase()}`}
                  error={!!validationErrors[field.name]}
                />
              )}

              {field.fieldType === "boolean" && (
                <Dropdown
                  fluid
                  selection
                  options={[
                    { key: "true", text: "Yes", value: true },
                    { key: "false", text: "No", value: false },
                  ]}
                  value={fieldValues[field.name] ?? false}
                  onChange={(_, { value }) =>
                    handleFieldChange(field.name, value as boolean)
                  }
                  placeholder={`Select ${field.label.toLowerCase()}`}
                  error={!!validationErrors[field.name]}
                />
              )}
            </FormField>
          ))}

          {Object.keys(validationErrors).length > 0 && (
            <Alert variant="error" title="Validation Errors">
              <ul>
                {Object.values(validationErrors).map((error, idx) => (
                  <li key={idx}>{error}</li>
                ))}
              </ul>
            </Alert>
          )}
        </>
      )}
    </div>
  );
};
