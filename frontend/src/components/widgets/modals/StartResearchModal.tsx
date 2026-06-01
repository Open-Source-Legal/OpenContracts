import React, { useState } from "react";
import { useMutation } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  Textarea,
} from "@os-legal/ui";
import { Sparkles, X } from "lucide-react";

import {
  START_RESEARCH_REPORT,
  StartResearchReportInput,
  StartResearchReportOutput,
} from "../../../graphql/mutations";
import {
  MAX_RESEARCH_PROMPT_CHARS,
  MAX_RESEARCH_TITLE_CHARS,
} from "../../../assets/configurations/constants";
import { getResearchReportUrl } from "../../../utils/navigationUtils";

interface StartResearchModalProps {
  corpusId: string;
  open: boolean;
  onClose: () => void;
}

/**
 * StartResearchModal - explicit (non-chat) kickoff for a deep-research job.
 *
 * The primary trigger is the corpus chat agent's start_deep_research tool;
 * this modal is a secondary affordance from the corpus Research tab. On
 * success it navigates to the new report's standalone page.
 */
export const StartResearchModal: React.FC<StartResearchModalProps> = ({
  corpusId,
  open,
  onClose,
}) => {
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");

  const [startResearch, { loading }] = useMutation<
    StartResearchReportOutput,
    StartResearchReportInput
  >(START_RESEARCH_REPORT);

  // Reset inputs on close so a dismissed-then-reopened modal starts blank
  // (otherwise the previous prompt/title would still be present and submittable).
  const handleClose = () => {
    setPrompt("");
    setTitle("");
    onClose();
  };

  const trimmedPrompt = prompt.trim();
  const tooLong = prompt.length > MAX_RESEARCH_PROMPT_CHARS;
  const canSubmit = trimmedPrompt.length > 0 && !tooLong && !loading;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    try {
      const res = await startResearch({
        variables: {
          corpusId,
          prompt: trimmedPrompt,
          title: title.trim() || undefined,
        },
      });
      const payload = res.data?.startResearchReport;
      if (payload?.ok && payload.obj) {
        toast.success(
          "Research started. We'll notify you when the report is ready."
        );
        handleClose();
        const url = getResearchReportUrl(payload.obj);
        if (url !== "#") {
          navigate(url);
        }
      } else {
        toast.error(payload?.message || "Could not start research.");
      }
    } catch (e) {
      console.error("Failed to start research report:", e);
      toast.error("Could not start research.");
    }
  };

  return (
    <Modal open={open} onClose={handleClose} size="md">
      <ModalHeader
        title={
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Sparkles size={20} />
            Start deep research
          </span>
        }
        onClose={handleClose}
      />
      <ModalBody>
        <Input
          label="Title (optional)"
          placeholder="e.g. Indemnification exposure"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={MAX_RESEARCH_TITLE_CHARS}
          fullWidth
        />
        <div style={{ marginTop: 16 }}>
          <Textarea
            label="What should the research agent investigate?"
            placeholder="Describe the question to research across this corpus. Be specific — this becomes the agent's instructions."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={6}
            maxLength={MAX_RESEARCH_PROMPT_CHARS}
            error={tooLong ? "Prompt is too long." : undefined}
            helperText={`${prompt.length} / ${MAX_RESEARCH_PROMPT_CHARS}`}
            fullWidth
          />
        </div>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onClick={handleClose}
          leftIcon={<X size={16} />}
        >
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={!canSubmit}
          leftIcon={<Sparkles size={16} />}
        >
          Start research
        </Button>
      </ModalFooter>
    </Modal>
  );
};

export default StartResearchModal;
