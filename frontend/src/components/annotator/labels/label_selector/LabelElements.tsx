import { Icon as SemanticIcon, Popup } from "semantic-ui-react";
import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import { Ban } from "lucide-react";
import { AnnotationLabelType } from "../../../../types/graphql-api";

const StyledCard = styled(Card)`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  margin: 0;
  flex: 1;
  max-width: 200px;
  min-width: 100px;
  user-select: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
`;

const BlankCard = styled(Card)`
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  margin: 0.25vw;
  width: 100%;
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

interface LabelCardProps {
  label: AnnotationLabelType;
}

export const SpanLabelCard = ({ label }: LabelCardProps) => {
  return (
    <StyledCard>
      <CardBody
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
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
                    name={label.icon}
                    style={{ color: label.color }}
                  />
                  <HeaderContent>{label.text}</HeaderContent>
                </SmallHeader>
              </div>
            </CardHeaderStyled>
          }
        />
      </CardBody>
    </StyledCard>
  );
};

export const BlankLabelElement = () => {
  return (
    <BlankCard>
      <CardBody
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "row",
          justifyContent: "center",
        }}
      >
        <div style={{ textAlign: "left" }}>
          <SmallHeader>
            <Ban size={16} style={{ marginRight: "0.5rem" }} />
            <HeaderContent>No Label Selected</HeaderContent>
          </SmallHeader>
        </div>
      </CardBody>
    </BlankCard>
  );
};
