import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import { AnalysisType } from "../../../types/graphql-api";

const MiniImage = styled.img`
  width: 35px;
  height: 35px;
  float: right;
  object-fit: contain;
`;

const CardHeader = styled.div`
  font-weight: 600;
  font-size: 1.1rem;
  margin-bottom: 0.25rem;
`;

const CardMeta = styled.div`
  color: #666;
  font-size: 0.9rem;
`;

export const SelectedAnalysisCard = () => {
  return (
    <Card
      style={{
        margin: "auto",
        width: "75%",
        height: "6vh",
      }}
    >
      <CardBody>
        <MiniImage
          src="https://react.semantic-ui.com/images/avatar/large/steve.jpg"
          alt="Profile"
        />
        <CardHeader>Steve Sanders</CardHeader>
        <CardMeta>Friends of Elliot</CardMeta>
      </CardBody>
    </Card>
  );
};
