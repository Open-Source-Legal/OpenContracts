import styled from "styled-components";

export const ShadowBoxDiv = styled.div`
  box-shadow:
    0 4px 8px 0 rgba(0, 0, 0, 0.2),
    0 6px 20px 0 rgba(0, 0, 0, 0.19);
`;

export const VerticallyCenteredDiv = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
  width: 100%;
`;

export const HorizontallyCenteredDiv = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: center;
  height: 100%;
  width: 100%;
`;

export const HorizontallyJustifiedDiv = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  height: 100%;
  width: 100%;
`;

export const FullWidthHorizontallyCenteredDiv = styled.div`
  display: flex;
  width: 100%;
  flex-direction: row;
  justify-content: center;
`;
