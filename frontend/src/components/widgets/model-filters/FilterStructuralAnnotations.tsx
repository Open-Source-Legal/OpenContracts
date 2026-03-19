import { useReactiveVar } from "@apollo/client";
import { Chip } from "@os-legal/ui";
import Select, { SelectOption } from "../../common/Select";
import { filterToStructuralAnnotations } from "../../../graphql/cache";
import { SingleValue, MultiValue } from "react-select";

interface FilterToStructuralAnnotationsSelectorProps {
  style?: Record<string, any>;
}

export const FilterToStructuralAnnotationsSelector = ({
  style,
}: FilterToStructuralAnnotationsSelectorProps) => {
  // Get the current value of the reactive variable
  const structural_filter = useReactiveVar(filterToStructuralAnnotations);

  // Options for the dropdown
  const structuralOptions: SelectOption[] = [
    { value: "ONLY", label: "Only Structural" },
    { value: "EXCLUDE", label: "Exclude Structural" },
    { value: "INCLUDE", label: "Include Structural" },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.375rem",
        width: "100%",
        position: "relative",
        ...style,
      }}
    >
      <Chip
        size="sm"
        variant="filled"
        style={{
          margin: "0",
          background: "linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)",
          color: "white",
          fontWeight: "600",
          fontSize: "0.75rem",
          letterSpacing: "0.025em",
          textTransform: "uppercase",
          boxShadow: "0 2px 4px rgba(168, 237, 234, 0.3)",
        }}
      >
        Structural Annotations
      </Chip>
      <div style={{ position: "relative", zIndex: 10 }}>
        <Select
          options={structuralOptions}
          onChange={(
            selectedOption: SingleValue<SelectOption> | MultiValue<SelectOption>
          ) => {
            // Update the reactive variable when a selection is made
            // This is a single select, so we know it's SingleValue
            const singleValue = selectedOption as SingleValue<SelectOption>;
            if (singleValue && !Array.isArray(singleValue)) {
              filterToStructuralAnnotations(
                singleValue.value as "ONLY" | "INCLUDE" | "EXCLUDE"
              );
            } else {
              filterToStructuralAnnotations(undefined);
            }
          }}
          placeholder="Filter structural annotations..."
          value={
            structural_filter
              ? structuralOptions.find((opt) => opt.value === structural_filter)
              : null
          }
        />
      </div>
    </div>
  );
};
