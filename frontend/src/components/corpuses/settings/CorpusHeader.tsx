/**
 * CorpusHeader - Header section with title, description, and edit button
 */
import React from "react";
import { Button } from "@os-legal/ui";
import { Edit } from "lucide-react";
import { editingCorpus } from "../../../graphql/cache";
import { CorpusType } from "../../../types/graphql-api";
import { SafeMarkdown } from "../../knowledge_base/markdown/SafeMarkdown";
import {
  CorpusHeaderContainer,
  TitleArea,
  CorpusTitle,
  CorpusDescription,
} from "../styles/corpusSettingsStyles";

interface CorpusHeaderProps {
  corpus: {
    id: string;
    title: string;
    description: string;
  };
}

export const CorpusHeader: React.FC<CorpusHeaderProps> = ({ corpus }) => {
  const displayContent = corpus.description;

  return (
    <CorpusHeaderContainer>
      <TitleArea>
        <CorpusTitle>{corpus.title}</CorpusTitle>
        <CorpusDescription>
          {displayContent ? (
            <SafeMarkdown>{displayContent}</SafeMarkdown>
          ) : (
            "No description provided."
          )}
        </CorpusDescription>
      </TitleArea>
      <Button
        variant="primary"
        onClick={() => editingCorpus(corpus as unknown as CorpusType)}
      >
        <Edit size={16} style={{ marginRight: "0.5rem" }} />
        Edit
      </Button>
    </CorpusHeaderContainer>
  );
};
