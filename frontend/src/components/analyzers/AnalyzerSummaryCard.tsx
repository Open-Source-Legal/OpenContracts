import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import { Users, Mail } from "lucide-react";
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

const InfoList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;
`;

const InfoListItem = styled.li`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
`;

const DependencyList = styled.ol`
  padding-left: 1.5rem;
  margin: 0.5rem 0 0 0;
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
        <InfoList>
          <InfoListItem>
            <Users size={16} />
            <span>
              Creator: {analyzer?.manifest?.metadata?.author_name ?? "Unknown"}
            </span>
          </InfoListItem>
          {analyzer?.manifest?.metadata?.author_email && (
            <InfoListItem>
              <Mail size={16} />
              <span>Email: {analyzer.manifest.metadata.author_email}</span>
            </InfoListItem>
          )}
        </InfoList>
      </CardBody>
      {dependency_list ? (
        <ExtraContent>
          <strong>Python Dependencies</strong>
          <DependencyList>
            {dependency_list.map((dependency, index) => (
              <li key={index}>{dependency}</li>
            ))}
          </DependencyList>
        </ExtraContent>
      ) : (
        <></>
      )}
    </AnalyzerCard>
  );
};
