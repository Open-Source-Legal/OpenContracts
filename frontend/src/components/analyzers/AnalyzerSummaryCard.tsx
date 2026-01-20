import { List, Header } from "semantic-ui-react";
import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import analyzer_icon from "../../assets/icons/noun-epicyclic-gearing-800132.png";
import { AnalyzerType, CorpusType } from "../../types/graphql-api";
import { LoadingOverlay } from "../common/LoadingOverlay";

const MiniImage = styled.img`
  width: 35px;
  height: 35px;
  float: right;
  object-fit: contain;
`;

const AnalyzerCard = styled(Card)`
  position: relative;
  cursor: pointer;
`;

const CardHeader = styled.div`
  font-weight: 600;
  font-size: 1.1rem;
  margin-bottom: 0.5rem;
`;

const CardMeta = styled.div`
  color: #666;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
`;

const CardDescription = styled.div`
  color: #333;
  margin-bottom: 1rem;
`;

const ExtraContent = styled(CardBody)`
  background: #f9f9f9;
  border-top: 1px solid #e0e0e0;
`;

export interface AnalyzerSummaryCardInputs {
  analyzer: AnalyzerType;
  corpus?: CorpusType;
  selected?: boolean;
  onSelect?: () => any | never;
}

export const AnalyzerSummaryCard = ({
  analyzer,
  corpus,
  selected,
  onSelect,
}: AnalyzerSummaryCardInputs) => {
  const dependency_list = analyzer?.manifest?.metadata?.dependencies
    ? analyzer.manifest.metadata.dependencies
    : [];

  const already_used = corpus?.appliedAnalyzerIds
    ? corpus.appliedAnalyzerIds.includes(
        analyzer?.analyzerId ? analyzer.analyzerId : ""
      )
    : false;

  return (
    <AnalyzerCard
      onClick={() => (onSelect && !already_used ? onSelect() : {})}
      style={selected ? { backgroundColor: "#e2ffdb" } : {}}
    >
      {already_used && (
        <LoadingOverlay
          active={true}
          content={
            <div style={{ textAlign: "center" }}>
              <h4>Analyzer Already Used...</h4>
              <div style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>
                Delete Analysis at the Corpus Level and Re-Rerun If Desired...
              </div>
            </div>
          }
        />
      )}
      <CardBody>
        <MiniImage src={analyzer_icon} alt="Analyzer Icon" />
        <CardHeader>
          {analyzer.manifest?.metadata?.title
            ? analyzer.manifest.metadata.title
            : ""}
        </CardHeader>
        <CardMeta>{analyzer.analyzerId}</CardMeta>
        <CardDescription>{analyzer.description}</CardDescription>
      </CardBody>
      <CardBody>
        <List>
          <List.Item>
            <List.Icon name="users" />
            <List.Content>
              Creator: {analyzer?.manifest?.metadata?.author_name ?? "Unknown"}
            </List.Content>
          </List.Item>
          {analyzer?.manifest?.metadata?.author_email && (
            <List.Item>
              <List.Icon name="mail" />
              <List.Content>
                Email: {analyzer.manifest.metadata.author_email}
              </List.Content>
            </List.Item>
          )}
        </List>
      </CardBody>
      {dependency_list ? (
        <ExtraContent>
          <strong>Python Dependencies</strong>
          <List ordered>
            {dependency_list.map((dependency, index) => (
              <List.Item key={index}>{dependency}</List.Item>
            ))}
          </List>
        </ExtraContent>
      ) : (
        <></>
      )}
    </AnalyzerCard>
  );
};
