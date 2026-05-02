/**
 * NewIterationDialog
 *
 * Compact modal that lets the user fork an existing extract along one of
 * three eval axes (model, document versions, or fieldset). The heavy
 * lifting lives server-side in `createExtractIteration`; this component is
 * just a focused form.
 */

import React, { useState } from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import { motion } from "framer-motion";
import { X, Cpu, FileStack, Sliders, Play } from "lucide-react";
import { Button } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { ExtractIterationAxis } from "../../../graphql/mutations";

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 2rem;
`;

const Container = styled(motion.div)`
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.18);
  width: 100%;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const Header = styled.div`
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const Title = styled.h3`
  margin: 0;
  font-size: 1.125rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const Body = styled.div`
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const AxisGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0.5rem;

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
`;

const AxisCard = styled.button<{ $active: boolean }>`
  border: 1px solid
    ${({ $active }) =>
      $active ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  background: ${({ $active }) =>
    $active ? "rgba(59, 130, 246, 0.06)" : "white"};
  border-radius: 10px;
  padding: 0.875rem 0.75rem;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  transition: all 0.15s;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const AxisLabel = styled.div`
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: flex;
  align-items: center;
  gap: 0.375rem;
`;

const AxisHint = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  line-height: 1.35;
`;

const Field = styled.label`
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Input = styled.input`
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: white;

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const Footer = styled.div`
  padding: 1rem 1.5rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.gray50};
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
`;

const Toggle = styled.label`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
`;

const CloseBtn = styled.button`
  border: none;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
`;

// Axis -> presentational descriptor. Kept here so the rest of the app
// doesn't need to know which icons/labels to show per axis.
const AXIS_OPTIONS: Array<{
  axis: ExtractIterationAxis;
  label: string;
  hint: string;
  Icon: typeof Cpu;
}> = [
  {
    axis: "MODEL",
    label: "Model",
    hint: "Same docs + schema. Compare model drift.",
    Icon: Cpu,
  },
  {
    axis: "DOCUMENT_VERSIONS",
    label: "Document versions",
    hint: "Re-run on the latest version of each document.",
    Icon: FileStack,
  },
  {
    axis: "FIELDSET",
    label: "Schema",
    hint: "Clone the schema so you can tweak prompts/types.",
    Icon: Sliders,
  },
];

export interface NewIterationDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (input: {
    axis: ExtractIterationAxis;
    name?: string;
    modelConfig?: Record<string, unknown>;
    autoStart: boolean;
  }) => void;
  defaultAxis?: ExtractIterationAxis;
  /** Pre-fills the model config field for MODEL-axis runs. */
  parentModel?: string | null;
  loading?: boolean;
}

export const NewIterationDialog: React.FC<NewIterationDialogProps> = ({
  open,
  onClose,
  onSubmit,
  defaultAxis = "MODEL",
  parentModel,
  loading,
}) => {
  const [axis, setAxis] = useState<ExtractIterationAxis>(defaultAxis);
  const [name, setName] = useState("");
  const [model, setModel] = useState(parentModel ?? "");
  const [autoStart, setAutoStart] = useState(true);

  if (!open) return null;

  const submit = () => {
    const modelConfig =
      axis === "MODEL" && model ? { model: model.trim() } : undefined;
    onSubmit({
      axis,
      name: name.trim() || undefined,
      modelConfig,
      autoStart,
    });
  };

  return createPortal(
    <Overlay role="dialog" aria-modal="true" aria-label="New iteration">
      <Container
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15 }}
      >
        <Header>
          <Title>New iteration</Title>
          <CloseBtn aria-label="Close" onClick={onClose}>
            <X size={18} />
          </CloseBtn>
        </Header>

        <Body>
          <Field as="div">
            <span>What are you testing?</span>
            <AxisGrid>
              {AXIS_OPTIONS.map(({ axis: a, label, hint, Icon }) => (
                <AxisCard
                  key={a}
                  type="button"
                  $active={axis === a}
                  onClick={() => setAxis(a)}
                >
                  <AxisLabel>
                    <Icon size={14} /> {label}
                  </AxisLabel>
                  <AxisHint>{hint}</AxisHint>
                </AxisCard>
              ))}
            </AxisGrid>
          </Field>

          <Field>
            Name (optional)
            <Input
              placeholder="Defaults to <source name> (iteration N)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>

          {axis === "MODEL" && (
            <Field>
              Model identifier
              <Input
                placeholder="e.g. anthropic:claude-opus-4-7"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </Field>
          )}
        </Body>

        <Footer>
          <Toggle>
            <input
              type="checkbox"
              checked={autoStart}
              onChange={(e) => setAutoStart(e.target.checked)}
            />
            Run immediately
          </Toggle>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Play size={12} />}
              onClick={submit}
              disabled={loading}
            >
              Create iteration
            </Button>
          </div>
        </Footer>
      </Container>
    </Overlay>,
    document.body
  );
};
