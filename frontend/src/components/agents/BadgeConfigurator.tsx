import React, { useState } from "react";
import styled from "styled-components";
import { Input } from "@os-legal/ui";
import {
  Bot,
  Brain,
  FileText,
  Database,
  Search,
  MessageSquare,
  Sparkles,
  Zap,
  BookOpen,
  Code,
  Lightbulb,
  Target,
  Microscope,
  Wrench,
  Shield,
  Globe,
  type LucideIcon,
} from "lucide-react";

// Available icons for agent badges
const AVAILABLE_ICONS: { name: string; icon: LucideIcon; label: string }[] = [
  { name: "bot", icon: Bot, label: "Robot" },
  { name: "brain", icon: Brain, label: "Brain" },
  { name: "sparkles", icon: Sparkles, label: "Sparkles" },
  { name: "zap", icon: Zap, label: "Lightning" },
  { name: "file-text", icon: FileText, label: "Document" },
  { name: "database", icon: Database, label: "Database" },
  { name: "search", icon: Search, label: "Search" },
  { name: "message-square", icon: MessageSquare, label: "Chat" },
  { name: "book-open", icon: BookOpen, label: "Book" },
  { name: "code", icon: Code, label: "Code" },
  { name: "lightbulb", icon: Lightbulb, label: "Idea" },
  { name: "target", icon: Target, label: "Target" },
  { name: "microscope", icon: Microscope, label: "Research" },
  { name: "wrench", icon: Wrench, label: "Tools" },
  { name: "shield", icon: Shield, label: "Shield" },
  { name: "globe", icon: Globe, label: "Global" },
];

// Preset colors for badges
const PRESET_COLORS = [
  { name: "Blue", value: "#3b82f6" },
  { name: "Purple", value: "#8b5cf6" },
  { name: "Indigo", value: "#6366f1" },
  { name: "Pink", value: "#ec4899" },
  { name: "Rose", value: "#f43f5e" },
  { name: "Orange", value: "#f97316" },
  { name: "Amber", value: "#f59e0b" },
  { name: "Green", value: "#22c55e" },
  { name: "Teal", value: "#14b8a6" },
  { name: "Cyan", value: "#06b6d4" },
  { name: "Slate", value: "#64748b" },
  { name: "Gray", value: "#6b7280" },
];

export interface BadgeConfig {
  icon: string;
  color: string;
  label: string;
}

interface BadgeConfiguratorProps {
  value: BadgeConfig;
  onChange: (config: BadgeConfig) => void;
}

const Container = styled.div`
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem;
  background: #f8fafc;
`;

const PreviewSection = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e2e8f0;
`;

const BadgePreview = styled.div<{ $color: string }>`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  border-radius: 9999px;
  background: ${(props) => props.$color}20;
  color: ${(props) => props.$color};
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid ${(props) => props.$color}40;

  svg {
    width: 14px;
    height: 14px;
  }
`;

const PreviewLabel = styled.span`
  font-size: 0.8rem;
  color: #64748b;
`;

const SectionTitle = styled.h4`
  font-size: 0.8rem;
  font-weight: 600;
  color: #475569;
  margin: 0 0 0.5rem 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const IconGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 0.5rem;
  margin-bottom: 1rem;

  @media (max-width: 768px) {
    grid-template-columns: repeat(4, 1fr);
  }
`;

const IconButton = styled.button<{ $selected: boolean; $color: string }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  padding: 0.5rem;
  border: 2px solid ${(props) => (props.$selected ? props.$color : "#e2e8f0")};
  border-radius: 8px;
  background: ${(props) => (props.$selected ? `${props.$color}10` : "white")};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: ${(props) => props.$color};
    background: ${(props) => `${props.$color}10`};
  }

  svg {
    width: 20px;
    height: 20px;
    color: ${(props) => (props.$selected ? props.$color : "#64748b")};
  }

  span {
    font-size: 0.65rem;
    color: ${(props) => (props.$selected ? props.$color : "#94a3b8")};
  }
`;

const ColorGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
`;

const ColorButton = styled.button<{ $color: string; $selected: boolean }>`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: ${(props) => props.$color};
  border: 3px solid ${(props) => (props.$selected ? "#1e293b" : "transparent")};
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    transform: scale(1.1);
  }

  ${(props) =>
    props.$selected &&
    `
    &::after {
      content: "✓";
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: white;
      font-size: 14px;
      font-weight: bold;
      text-shadow: 0 1px 2px rgba(0,0,0,0.3);
    }
  `}
`;

const CustomColorInput = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const ColorInputWrapper = styled.div`
  position: relative;
  width: 32px;
  height: 32px;

  input[type="color"] {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
  }
`;

const ColorSwatch = styled.div<{ $color: string }>`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: ${(props) => props.$color};
  border: 2px dashed #cbd5e1;
`;

const LabelInputWrapper = styled.div`
  margin-top: 0.5rem;

  .ui.input {
    width: 200px;
  }
`;

// Helper to get icon component by name
const getIconComponent = (name: string): LucideIcon => {
  const found = AVAILABLE_ICONS.find((i) => i.name === name);
  return found?.icon || Bot;
};

export const BadgeConfigurator: React.FC<BadgeConfiguratorProps> = ({
  value,
  onChange,
}) => {
  const [showCustomColor, setShowCustomColor] = useState(
    !PRESET_COLORS.some((c) => c.value === value.color)
  );

  const IconComponent = getIconComponent(value.icon);

  const handleIconChange = (iconName: string) => {
    onChange({ ...value, icon: iconName });
  };

  const handleColorChange = (color: string) => {
    onChange({ ...value, color });
    setShowCustomColor(false);
  };

  const handleCustomColorChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...value, color: e.target.value });
    setShowCustomColor(true);
  };

  const handleLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...value, label: e.target.value });
  };

  return (
    <Container>
      {/* Preview */}
      <PreviewSection>
        <PreviewLabel>Preview:</PreviewLabel>
        <BadgePreview $color={value.color}>
          <IconComponent />
          <span>{value.label || "Agent"}</span>
        </BadgePreview>
      </PreviewSection>

      {/* Icon Selection */}
      <SectionTitle>Icon</SectionTitle>
      <IconGrid>
        {AVAILABLE_ICONS.map(({ name, icon: Icon, label }) => (
          <IconButton
            key={name}
            type="button"
            $selected={value.icon === name}
            $color={value.color}
            onClick={() => handleIconChange(name)}
            title={label}
          >
            <Icon />
            <span>{label}</span>
          </IconButton>
        ))}
      </IconGrid>

      {/* Color Selection */}
      <SectionTitle>Color</SectionTitle>
      <ColorGrid>
        {PRESET_COLORS.map(({ name, value: colorValue }) => (
          <ColorButton
            key={colorValue}
            type="button"
            $color={colorValue}
            $selected={value.color === colorValue && !showCustomColor}
            onClick={() => handleColorChange(colorValue)}
            title={name}
          />
        ))}
        <CustomColorInput>
          <ColorInputWrapper>
            <ColorSwatch $color={showCustomColor ? value.color : "#cbd5e1"} />
            <input
              type="color"
              value={value.color}
              onChange={handleCustomColorChange}
              title="Custom color"
            />
          </ColorInputWrapper>
        </CustomColorInput>
      </ColorGrid>

      {/* Label Input */}
      <SectionTitle>Label Text</SectionTitle>
      <LabelInputWrapper>
        <Input
          placeholder="AI Assistant"
          value={value.label}
          onChange={handleLabelChange}
          maxLength={20}
          helperText="Short label shown on the badge (max 20 chars)"
        />
      </LabelInputWrapper>
    </Container>
  );
};

export default BadgeConfigurator;
