import React, { useState } from "react";
import { Alert, Button, Textarea } from "@os-legal/ui";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
import {
  UPDATE_CORPUS,
  UpdateCorpusInputs,
  UpdateCorpusOutputs,
} from "../../graphql/mutations";

interface CorpusAgentSettingsProps {
  corpusId: string;
  corpusAgentInstructions?: string | null;
  documentAgentInstructions?: string | null;
  canUpdate: boolean;
}

const Container = styled.div`
  padding: 1.5rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
`;

const Section = styled.div`
  margin-bottom: 2rem;

  &:last-child {
    margin-bottom: 0;
  }
`;

const SectionHeader = styled.div`
  margin-bottom: 1rem;
`;

const HelperText = styled.p`
  color: #64748b;
  font-size: 0.875rem;
  margin: 0.5rem 0;
  line-height: 1.5;
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
`;

const MainHeading = styled.h3`
  font-size: 1.25rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.5rem 0;
`;

const SubHeading = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.5rem 0;
`;

export const CorpusAgentSettings: React.FC<CorpusAgentSettingsProps> = ({
  corpusId,
  corpusAgentInstructions,
  documentAgentInstructions,
  canUpdate,
}) => {
  const [corpusInstructions, setCorpusInstructions] = useState(
    corpusAgentInstructions || ""
  );
  const [documentInstructions, setDocumentInstructions] = useState(
    documentAgentInstructions || ""
  );
  const [hasChanges, setHasChanges] = useState(false);

  const [updateCorpus, { loading }] = useMutation<
    UpdateCorpusOutputs,
    UpdateCorpusInputs
  >(UPDATE_CORPUS, {
    onCompleted: (data) => {
      if (data.updateCorpus.ok) {
        toast.success("Agent instructions updated successfully");
        setHasChanges(false);
      } else {
        toast.error(
          `Failed to update: ${data.updateCorpus.message || "Unknown error"}`
        );
      }
    },
    onError: (error) => {
      toast.error(`Error: ${error.message}`);
    },
  });

  const handleCorpusInstructionsChange = (value: string) => {
    setCorpusInstructions(value);
    setHasChanges(
      value !== (corpusAgentInstructions || "") ||
        documentInstructions !== (documentAgentInstructions || "")
    );
  };

  const handleDocumentInstructionsChange = (value: string) => {
    setDocumentInstructions(value);
    setHasChanges(
      value !== (documentAgentInstructions || "") ||
        corpusInstructions !== (corpusAgentInstructions || "")
    );
  };

  const handleSave = () => {
    updateCorpus({
      variables: {
        id: corpusId,
        corpusAgentInstructions: corpusInstructions || undefined,
        documentAgentInstructions: documentInstructions || undefined,
      },
    });
  };

  const handleReset = () => {
    setCorpusInstructions(corpusAgentInstructions || "");
    setDocumentInstructions(documentAgentInstructions || "");
    setHasChanges(false);
  };

  if (!canUpdate) {
    return (
      <Container>
        <Alert variant="info">
          You do not have permission to update agent instructions for this
          corpus.
        </Alert>
      </Container>
    );
  }

  return (
    <Container>
      <MainHeading>Agent Instructions</MainHeading>
      <HelperText>
        Customize how AI agents behave when analyzing this corpus and its
        documents. Leave blank to use system defaults.
      </HelperText>

      <form>
        <Section>
          <SectionHeader>
            <SubHeading>Corpus Agent Instructions</SubHeading>
            <HelperText>
              Controls how the corpus-level agent behaves when answering
              questions about the collection of documents. Default instructions
              tell the agent to examine available documents when the corpus
              description is empty.
            </HelperText>
          </SectionHeader>
          <Textarea
            placeholder="Leave blank to use default instructions..."
            value={corpusInstructions}
            onChange={(e) => handleCorpusInstructionsChange(e.target.value)}
            rows={8}
            style={{ fontFamily: "monospace", fontSize: "0.9rem" }}
            fullWidth
          />
        </Section>

        <Section>
          <SectionHeader>
            <SubHeading>Document Agent Instructions</SubHeading>
            <HelperText>
              Controls how document-level agents behave when analyzing
              individual documents in this corpus. Default instructions
              emphasize using tools and citing sources with page numbers.
            </HelperText>
          </SectionHeader>
          <Textarea
            placeholder="Leave blank to use default instructions..."
            value={documentInstructions}
            onChange={(e) => handleDocumentInstructionsChange(e.target.value)}
            rows={8}
            style={{ fontFamily: "monospace", fontSize: "0.9rem" }}
            fullWidth
          />
        </Section>

        {hasChanges && (
          <ButtonGroup>
            <Button variant="primary" onClick={handleSave} loading={loading}>
              Save Changes
            </Button>
            <Button
              variant="secondary"
              onClick={handleReset}
              disabled={loading}
            >
              Reset
            </Button>
          </ButtonGroup>
        )}
      </form>
    </Container>
  );
};
