export class RGB {
  // eslint-disable-next-line no-useless-constructor, no-empty-function
  constructor(
    public r: number,
    public g: number,
    public b: number
  ) {}

  toString() {
    return `rgb(${this.r},${this.g},${this.b})`;
  }
}

// convert a hex color string to a RGB
export function hexToRgb(hex: string): RGB {
  // Expand shorthand form (e.g. "03F") to full form (e.g. "0033FF")
  const shorthandRegex = /^#?([\da-f])([\da-f])([\da-f])$/i;
  hex = hex.replace(shorthandRegex, (_, r, g, b) => {
    // eslint-disable no-unused-vars
    return r + r + g + g + b + b;
  });
  const result = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex);
  return result
    ? new RGB(
        parseInt(result[1], 16),
        parseInt(result[2], 16),
        parseInt(result[3], 16)
      )
    : new RGB(0, 0, 0);
}

export class Color {
  public rgb: RGB;

  constructor(
    public displayName: string,
    public hex: string,
    public useContrastText?: boolean
  ) {
    this.hex = hex.toUpperCase();
    this.rgb = hexToRgb(hex);
  }

  toString() {
    return this.hex;
  }
}

export const color: Record<string, string> = {
  R1: "#FFF2F2",
  R2: "#FFE1E0",
  R3: "#FDC1C0",
  R4: "#FF9F9E",
  R5: "#F9807F",
  R6: "#F7605F",
  R7: "#E7504F",
  R8: "#D63F3F",
  R9: "#BF2D2D",
  R10: "#932222",
  O1: "#FFF9E8",
  O2: "#FFF1C4",
  O3: "#FFE394",
  O4: "#FFD45D",
  O5: "#FFC72E",
  O6: "#FFBB00",
  O7: "#FFA200",
  O8: "#FF9100",
  O9: "#DD6502",
  O10: "#A94006",
  G1: "#E4FFF7",
  G2: "#C1F7E6",
  G3: "#98EAD0",
  G4: "#70DDBA",
  G5: "#47CFA4",
  G6: "#1EC28E",
  G7: "#14A87D",
  G8: "#0A8F6B",
  G9: "#00755A",
  G10: "#005340",
  T1: "#E6FDFE",
  T2: "#C6F3F6",
  T3: "#9AE7EC",
  T4: "#6EDCE3",
  T5: "#42D0D9",
  T6: "#16C4CF",
  T7: "#0FA9B6",
  T8: "#078E9E",
  T9: "#007385",
  T10: "#004752",
  A1: "#F2FCFF",
  A2: "#E0F9FF",
  A3: "#B5F0FF",
  A4: "#85E9FF",
  A5: "#4DE1FF",
  A6: "#00D5FF",
  A7: "#00C1E8",
  A8: "#01A2CA",
  A9: "#0278A7",
  A10: "#054976",
  B1: "#F0F7FF",
  B2: "#D5EAFE",
  B3: "#80BDFF",
  B4: "#2F85F7",
  B5: "#2376E5",
  B6: "#265ED4",
  B7: "#1A4CAE",
  B8: "#1B4596",
  B9: "#1D3D7E",
  B10: "#223367",
  P1: "#F8F7FD",
  P2: "#E6E3F7",
  P3: "#CFC9F1",
  P4: "#B7AFEB",
  P5: "#A094E4",
  P6: "#887ADE",
  P7: "#7265C1",
  P8: "#5C50A4",
  P9: "#463B87",
  P10: "#271F55",
  M1: "#FDF7FC",
  M2: "#F6DFF3",
  M3: "#EFC0E8",
  M4: "#E7A2DE",
  M5: "#E083D3",
  M6: "#D864C9",
  M7: "#BE54B0",
  M8: "#802579",
  M9: "#8A337E",
  M10: "#65295D",
  N1: "#FFFFFF",
  N2: "#F8F9FA",
  N3: "#F0F4F7",
  N4: "#E8ECF2",
  N5: "#D5DAE3",
  N6: "#AEB7C4",
  N7: "#8C96A3",
  N8: "#616C7A",
  N9: "#47515C",
  N10: "#303945",
  black: "#000",
  white: "#FFF",
  transparent: "transparent",
};

// use for charts and viz on top of images
export const chartingColor: Record<string, string> = {
  DarkBlue: "#2389ff",
  Green: "#2ff53a",
  Magenta: "#cf03e2",
  Orange: "#ff6c01",
  LightBlue: "#47daff",
  Red: "#f22b2b",
  Purple: "#7948ff",
  Yellow: "#fffc00",
  RoyalBlue: "#235dff",
  Teal: "#2fffa8",
  Pink: "#e73fa0",
  Tangerine: "#ffad06",
};
