import React from "react";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import ReactSelect, {
  Props as ReactSelectProps,
  StylesConfig,
  components,
  OptionProps,
  SingleValueProps,
} from "react-select";

export interface SelectOption {
  value: string;
  label: string;
  icon?: string;
  subheader?: string;
  content?: React.ReactNode;
}

interface SelectProps extends Omit<
  ReactSelectProps<SelectOption, boolean>,
  "styles"
> {
  customStyles?: StylesConfig<SelectOption, boolean>;
}

// Icon component for rendering URL icons as images
const IconImage: React.FC<{ src: string; size?: number }> = ({
  src,
  size = 20,
}) => (
  <img
    src={src}
    alt=""
    style={{
      width: size,
      height: size,
      borderRadius: 4,
      objectFit: "cover",
      flexShrink: 0,
    }}
  />
);

// Custom option component to support icons and subheaders
const CustomOption: React.FC<OptionProps<SelectOption, boolean>> = (props) => {
  const { data } = props;

  return (
    <components.Option {...props}>
      {data.content ? (
        data.content
      ) : (
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {data.icon && <IconImage src={data.icon} />}
            <span style={{ fontWeight: 500 }}>{data.label}</span>
          </div>
          {data.subheader && (
            <div
              style={{
                fontSize: "0.8125rem",
                color: "rgba(0, 0, 0, 0.6)",
                marginLeft: data.icon ? "1.75rem" : "0",
              }}
            >
              {data.subheader}
            </div>
          )}
        </div>
      )}
    </components.Option>
  );
};

// Custom single value component to show icon in selected value
const CustomSingleValue: React.FC<SingleValueProps<SelectOption, boolean>> = (
  props
) => {
  const { data } = props;

  return (
    <components.SingleValue {...props}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        {data.icon && <IconImage src={data.icon} size={18} />}
        <span>{data.label}</span>
      </div>
    </components.SingleValue>
  );
};

export const Select: React.FC<SelectProps> = ({ customStyles, ...props }) => {
  const defaultStyles: StylesConfig<SelectOption, boolean> = {
    control: (base, state) => ({
      ...base,
      margin: 0,
      minWidth: "260px",
      fontSize: "0.875rem",
      background: "white",
      border: state.isFocused
        ? `1px solid ${OS_LEGAL_COLORS.primaryBlue}`
        : `1px solid ${OS_LEGAL_COLORS.border}`,
      borderRadius: "8px",
      boxShadow: state.isFocused
        ? `0 0 0 1px ${OS_LEGAL_COLORS.primaryBlue}`
        : "0 1px 2px rgba(0, 0, 0, 0.05)",
      transition: "all 0.2s ease",
      "&:hover": {
        borderColor: OS_LEGAL_COLORS.borderHover,
      },
      minHeight: "38px",
    }),
    menu: (base) => ({
      ...base,
      borderRadius: "8px",
      border: `1px solid ${OS_LEGAL_COLORS.border}`,
      boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
      overflow: "hidden",
      zIndex: 1000,
    }),
    menuList: (base) => ({
      ...base,
      padding: 0,
      maxHeight: "300px",
    }),
    option: (base, state) => ({
      ...base,
      padding: "0.75rem 1rem",
      fontSize: "0.875rem",
      backgroundColor: state.isSelected
        ? OS_LEGAL_COLORS.primaryBlue
        : state.isFocused
          ? "rgba(74, 144, 226, 0.1)"
          : "white",
      color: state.isSelected ? "white" : "rgba(0, 0, 0, 0.87)",
      cursor: "pointer",
      transition: "all 0.15s ease",
      "&:active": {
        backgroundColor: state.isSelected
          ? OS_LEGAL_COLORS.primaryBlueHover
          : "rgba(74, 144, 226, 0.2)",
      },
    }),
    placeholder: (base) => ({
      ...base,
      color: OS_LEGAL_COLORS.textMuted,
      fontSize: "0.875rem",
    }),
    singleValue: (base) => ({
      ...base,
      color: "rgba(0, 0, 0, 0.87)",
      fontSize: "0.875rem",
    }),
    multiValue: (base) => ({
      ...base,
      backgroundColor: OS_LEGAL_COLORS.infoSurface,
      borderRadius: "6px",
      border: `1px solid ${OS_LEGAL_COLORS.infoBorder}`,
      padding: "0.125rem 0.25rem",
    }),
    multiValueLabel: (base) => ({
      ...base,
      color: OS_LEGAL_COLORS.infoText,
      fontSize: "0.8125rem",
      fontWeight: 500,
      padding: "0.125rem 0.25rem",
    }),
    multiValueRemove: (base) => ({
      ...base,
      color: OS_LEGAL_COLORS.infoText,
      cursor: "pointer",
      "&:hover": {
        backgroundColor: OS_LEGAL_COLORS.infoBorder,
        color: OS_LEGAL_COLORS.infoText,
      },
      borderRadius: "0 4px 4px 0",
    }),
    input: (base) => ({
      ...base,
      color: "rgba(0, 0, 0, 0.87)",
      fontSize: "0.875rem",
    }),
    indicatorSeparator: (base) => ({
      ...base,
      display: "none",
    }),
    dropdownIndicator: (base, state) => ({
      ...base,
      color: state.isFocused
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.textMuted,
      transition: "all 0.2s ease",
      "&:hover": {
        color: OS_LEGAL_COLORS.primaryBlue,
      },
    }),
    clearIndicator: (base) => ({
      ...base,
      color: OS_LEGAL_COLORS.textMuted,
      cursor: "pointer",
      transition: "all 0.2s ease",
      "&:hover": {
        color: OS_LEGAL_COLORS.danger,
      },
    }),
    loadingIndicator: (base) => ({
      ...base,
      color: OS_LEGAL_COLORS.primaryBlue,
    }),
    noOptionsMessage: (base) => ({
      ...base,
      fontSize: "0.875rem",
      color: OS_LEGAL_COLORS.textMuted,
      padding: "1rem",
    }),
  };

  // Merge custom styles with defaults
  const mergedStyles: StylesConfig<SelectOption, boolean> = customStyles
    ? Object.keys(defaultStyles).reduce(
        (acc, key) => {
          const styleKey = key as keyof StylesConfig<SelectOption, boolean>;
          acc[styleKey] = (base: any, state: any) => {
            const defaultStyle =
              typeof defaultStyles[styleKey] === "function"
                ? (defaultStyles[styleKey] as any)(base, state)
                : base;
            const customStyle =
              customStyles[styleKey] &&
              typeof customStyles[styleKey] === "function"
                ? (customStyles[styleKey] as any)(base, state)
                : {};
            return { ...defaultStyle, ...customStyle };
          };
          return acc;
        },
        {} as StylesConfig<SelectOption, boolean>
      )
    : defaultStyles;

  return (
    <ReactSelect<SelectOption, boolean>
      {...props}
      styles={mergedStyles}
      components={{
        Option: CustomOption,
        SingleValue: CustomSingleValue,
        ...props.components,
      }}
      classNamePrefix="react-select"
    />
  );
};

export default Select;
