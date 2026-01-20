import { Icon as SemanticIcon, Popup } from "semantic-ui-react";
import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import { Trash2, Ban } from "lucide-react";
import { AnnotationLabelType } from "../../../../types/graphql-api";
import useWindowDimensions from "../../../hooks/WindowDimensionHook";
import { TruncatedText } from "../../../widgets/data-display/TruncatedText";

import "./DocTypeLabels.css";

const DocTypeLabelCard = styled(Card)`
  position: relative;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
`;

const CardHeaderStyled = styled.div`
  text-align: left;
  word-break: break-all;
  display: flex;
  flex-direction: row;
  justify-content: flex-start;
  height: 100%;
  margin: 0px;
`;

const FluidCard = styled(Card)`
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  margin: 0.25vw;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
`;

const SmallHeader = styled.h5`
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
  display: flex;
  align-items: center;
`;

const HeaderContent = styled.span`
  word-break: break-all;
`;

interface DocTypeLabelProps {
  label: AnnotationLabelType;
  onRemove: (() => void) | null;
}

export const DocTypeLabel = ({ label, onRemove }: DocTypeLabelProps) => {
  const { width } = useWindowDimensions();

  if (!label) {
    return <></>;
  }

  return (
    <DocTypeLabelCard className="DocTypeLabelCard">
      {onRemove ? (
        <Trash2
          size={16}
          style={{
            position: "absolute",
            right: ".25vw",
            top: ".25vw",
            color: "#db2828",
            cursor: "pointer",
          }}
          onClick={() => onRemove()}
        />
      ) : (
        <></>
      )}
      <CardBody className="DocTypeLabelContent">
        <Popup
          style={{ textAlign: "left" }}
          content={
            <p>
              <u>
                <b>
                  <em>Description:</em>
                </b>
              </u>
              <br />
              {`${label.description}`}
            </p>
          }
          trigger={
            <CardHeaderStyled>
              <div>
                <SmallHeader>
                  <SemanticIcon
                    className="DocTypeLabelIcon"
                    name={label.icon}
                    style={{ color: label.color }}
                  />
                  <HeaderContent className="DocTypeLabelHeader">
                    <TruncatedText
                      text={label?.text ? label.text : "MISSING"}
                      limit={width <= 400 ? 20 : width <= 768 ? 36 : 64}
                    />
                  </HeaderContent>
                </SmallHeader>
              </div>
            </CardHeaderStyled>
          }
        />
      </CardBody>
    </DocTypeLabelCard>
  );
};

export const BlankDocTypeLabel = () => {
  return (
    <FluidCard>
      <CardBody
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "row",
          justifyContent: "center",
        }}
      >
        <div style={{ textAlign: "left" }}>
          <SmallHeader>
            <Ban size={16} style={{ marginRight: "0.5rem" }} />
            <HeaderContent>No Label</HeaderContent>
          </SmallHeader>
        </div>
      </CardBody>
    </FluidCard>
  );
};
