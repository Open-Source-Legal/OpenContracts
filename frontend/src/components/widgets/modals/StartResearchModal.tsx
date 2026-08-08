import React, { useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  Select,
  Textarea,
} from "@os-legal/ui";
import { Sparkles, X } from "lucide-react";

import {
  START_RESEARCH_REPORT,
  StartResearchReportInput,
  StartResearchReportOutput,
} from "../../../graphql/mutations";
import {
  GET_CORPUS_GROUP_OPTIONS,
  CorpusGroupOptionsResult,
} from "../../corpus_groups/graphql";
import { ErrorMessage } from "../feedback";
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
  const [corpusGroupId, setCorpusGroupId] = useState("");

  const [startResearch, { loading }] = useMutation<
    StartResearchReportOutput,
    StartResearchReportInput
  >(START_RESEARCH_REPORT);

  // Only fetched while the modal is open — the picker is optional and most
  // runs never widen past the anchor corpus.
  const { data: groupData, error: groupError } =
    useQuery<CorpusGroupOptionsResult>(GET_CORPUS_GROUP_OPTIONS, {
      skip: !open,
      fetchPolicy: "cache-and-network",
    });
  const groupOptions = (groupData?.corpusGroups?.edges ?? []).map(
    ({ node }) => ({
      value: node.id,
      label: node.title,
    })
  );

  // Reset inputs on close so a dismissed-then-reopened modal starts blank
  // (otherwise the previous prompt/title would still be present and submittable).
  const handleClose = () => {
    setPrompt("");
    setTitle("");
    setCorpusGroupId("");
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
          corpusGroupId: corpusGroupId || undefined,
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
        {groupOptions.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Select
              label="Search a corpus group as well (optional)"
              placeholder="This corpus only"
              options={groupOptions}
              value={corpusGroupId}
              onChange={setCorpusGroupId}
              clearable
              searchable={groupOptions.length > 8}
              fullWidth
              helperText="The agent can reach every corpus in the group you may read — use this when the answer spans authorities (a statute in one corpus, the rule it authorises in another)."
            />
          </div>
        )}
        {groupError && (
          <ErrorMessage style={{ marginTop: 16 }}>
            Couldn't load corpus groups ({groupError.message}). You can still
            start research against this corpus alone.
          </ErrorMessage>
        )}
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
