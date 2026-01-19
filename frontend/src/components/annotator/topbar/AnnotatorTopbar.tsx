import React, { useRef, useLayoutEffect, useState } from "react";
import styled, { keyframes } from "styled-components";
import { ChevronUp } from "lucide-react";
import { AnalysisType, ExtractType } from "../../../types/graphql-api";
import { ExtractAndAnalysisHorizontalSelector } from "../../analyses/AnalysisSelectorForCorpus";
import { useAdditionalUIStates } from "../context/UISettingsAtom";

interface AnnotatorTopbarProps {
  analyses: AnalysisType[];
  extracts: ExtractType[];
  children?: React.ReactNode;
}

// Keyframes for icon animation
const rotateUp = keyframes`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(180deg);
  }
`;

const rotateDown = keyframes`
  from {
    transform: rotate(180deg);
  }
  to {
    transform: rotate(0deg);
  }
`;

const TopbarContainer = styled.div<{ visible: boolean; height: number }>`
  position: absolute;
  top: ${(props) => (props.visible ? "0" : `-${props.height}px`)};
  left: 0;
  right: 0;
  z-index: 3;
  background-color: #fff;
  transition: top 0.5s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const ToggleButton = styled.div<{ visible: boolean; topbarHeight: number }>`
  position: absolute;
  top: ${(props) => (props.visible ? `${props.topbarHeight - 20}px` : "20px")};
  right: 20px;
  z-index: 4;
  cursor: pointer;
  width: 40px;
  height: 40px;
  background-color: #4c4f52;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: top 0.5s ease;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);

  &:hover {
    background-color: #5a5e63;
  }

  .icon {
    color: rgba(255, 255, 255, 0.8);
    animation: ${(props) => (props.visible ? rotateUp : rotateDown)} 0.5s
      forwards;
  }
`;

export const AnnotatorTopbar: React.FC<AnnotatorTopbarProps> = ({
  analyses,
  extracts,
  children,
}) => {
  const topbarRef = useRef<HTMLDivElement>(null);
  const [topbarHeight, setTopbarHeight] = useState(0);
  const { topbarVisible, setTopbarVisible } = useAdditionalUIStates();

  useLayoutEffect(() => {
    if (topbarRef.current) {
      setTopbarHeight(topbarRef.current.offsetHeight);
    }
  }, [topbarVisible]);

  const toggleTopbar = () => {
    setTopbarVisible(!topbarVisible);
  };

  return (
    <div style={{ position: "relative" }}>
      <TopbarContainer
        ref={topbarRef}
        visible={topbarVisible}
        height={topbarHeight}
      >
        {/* Topbar Content */}
        <ExtractAndAnalysisHorizontalSelector
          read_only={false}
          analyses={analyses}
          extracts={extracts}
        />
      </TopbarContainer>

      <ToggleButton
        onClick={toggleTopbar}
        visible={topbarVisible}
        topbarHeight={topbarHeight}
      >
        <ChevronUp size={20} className="icon" />
      </ToggleButton>
    </div>
  );
};
