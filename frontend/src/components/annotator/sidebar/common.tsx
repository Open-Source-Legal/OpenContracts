import styled from "styled-components";

export const VerticallyCenteredDiv = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  margin: 0px;
`;

export const VerticallyJustifiedEndDiv = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  margin: 0px;
`;

export const HorizontallyCenteredDiv = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: center;
  margin: 0px;
`;

export const HorizontallyJustifiedDiv = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  margin: 0px;
`;

export const FullWidthHorizontallyCenteredDiv = styled.div`
  display: flex;
  width: 100%;
  flex-direction: row;
  justify-content: center;
  margin: 0px;
`;
