import styled from "styled-components";
import { Sketch } from "@uiw/react-color";

interface ColorPickerSegmentProps {
  color: string;
  setColor: (color: { hex: string }) => void;
  style?: Record<string, any>;
}

const ColorPickerContainer = styled.div`
  padding: 1rem;
  background: #fff;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-radius: 0.28571429rem;
  box-shadow: 0 1px 2px 0 rgba(34, 36, 38, 0.15);
`;

export const ColorPickerSegment = ({
  color,
  setColor,
  style,
}: ColorPickerSegmentProps) => {
  return (
    <ColorPickerContainer style={style ? style : { width: "20vw" }}>
      <Sketch color={color} onChange={setColor} />
    </ColorPickerContainer>
  );
};
