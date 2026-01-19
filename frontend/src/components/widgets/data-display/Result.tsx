import { Header } from "semantic-ui-react";
import styled from "styled-components";
import { ThumbsUp, AlertTriangle, HelpCircle, LucideIcon } from "lucide-react";

export const Result = ({
  status,
  title,
}: {
  status: "warning" | "success" | "unknown";
  title: string;
}) => {
  function convertStatusToIcon(status: string): {
    Icon: LucideIcon;
    color: string;
  } {
    switch (status) {
      case "success":
        return {
          Icon: ThumbsUp,
          color: "green",
        };
      case "warning":
        return {
          Icon: AlertTriangle,
          color: "#fbbd08",
        };
      case "unknown":
        return {
          Icon: HelpCircle,
          color: "black",
        };
      default:
        return {
          Icon: HelpCircle,
          color: "black",
        };
    }
  }

  const { Icon, color } = convertStatusToIcon(status);

  return (
    <ResultIndicatorContainer>
      <InnerContainer>
        <div style={{ marginBottom: "2vh" }}>
          <Icon size={64} color={color} />
        </div>
        <div>
          <Header as="h1" textAlign="center">
            {status}
            <Header.Subheader>{title}</Header.Subheader>
          </Header>
        </div>
      </InnerContainer>
    </ResultIndicatorContainer>
  );
};

const ResultIndicatorContainer = styled.div`
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: row;
  justify-content: center;
  align-items: center;
`;

const InnerContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
`;
