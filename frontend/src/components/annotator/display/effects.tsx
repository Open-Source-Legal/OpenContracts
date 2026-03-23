import { keyframes } from "styled-components";
import {
  APPROVED_RGB,
  REJECTED_RGB,
} from "../../../assets/configurations/constants";

const { r: gR, g: gG, b: gB } = APPROVED_RGB;
const { r: mR, g: mG, b: mB } = REJECTED_RGB;

export const pulseGreen = keyframes`
  0% {
    box-shadow: 0 0 10px 3px rgba(${gR}, ${gG}, ${gB}, 0.15),
               0 0 4px 1px rgba(${gR}, ${gG}, ${gB}, 0.10);
  }
  50% {
    box-shadow: 0 0 18px 6px rgba(${gR}, ${gG}, ${gB}, 0.22),
               0 0 6px 2px rgba(${gR}, ${gG}, ${gB}, 0.14);
  }
  100% {
    box-shadow: 0 0 10px 3px rgba(${gR}, ${gG}, ${gB}, 0.15),
               0 0 4px 1px rgba(${gR}, ${gG}, ${gB}, 0.10);
  }
`;

export const pulseMaroon = keyframes`
  0% {
    box-shadow: 0 0 10px 3px rgba(${mR}, ${mG}, ${mB}, 0.15),
               0 0 4px 1px rgba(${mR}, ${mG}, ${mB}, 0.10);
  }
  50% {
    box-shadow: 0 0 18px 6px rgba(${mR}, ${mG}, ${mB}, 0.22),
               0 0 6px 2px rgba(${mR}, ${mG}, ${mB}, 0.14);
  }
  100% {
    box-shadow: 0 0 10px 3px rgba(${mR}, ${mG}, ${mB}, 0.15),
               0 0 4px 1px rgba(${mR}, ${mG}, ${mB}, 0.10);
  }
`;
