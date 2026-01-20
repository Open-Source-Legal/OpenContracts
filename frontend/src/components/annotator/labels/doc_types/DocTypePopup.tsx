import React, { useState } from "react";
import { Input } from "semantic-ui-react";
import { Button } from "@os-legal/ui";
import styled from "styled-components";
import Fuse from "fuse.js";
import { Search, Tag, SearchX } from "lucide-react";
import { AnnotationLabelType } from "../../../../types/graphql-api";

const PopupContainer = styled.div`
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 12px;
  overflow: hidden;
  width: 320px;
`;

const SearchContainer = styled.div`
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa, #e9ecef);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
`;

const StyledInput = styled(Input)`
  &.ui.input {
    width: 100%;

    input {
      border-radius: 8px !important;
      border: 1px solid rgba(0, 0, 0, 0.1) !important;
      padding: 8px 16px !important;
      transition: all 0.2s ease !important;

      &:focus {
        border-color: #00b09b !important;
        box-shadow: 0 0 0 2px rgba(0, 176, 155, 0.2) !important;
      }
    }
  }
`;

const LabelsContainer = styled.div`
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background-color: rgba(155, 155, 155, 0.5);
    border-radius: 20px;
    border: transparent;
  }
`;

const LabelCard = styled.div<{ selected: boolean }>`
  padding: 12px;
  margin: 8px 4px;
  background: ${(props) =>
    props.selected ? "linear-gradient(135deg, #00b09b15, #96c93d15)" : "white"};
  border: 1px solid
    ${(props) => (props.selected ? "#00b09b" : "rgba(0,0,0,0.05)")};
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    border-color: ${(props) => (props.selected ? "#00b09b" : "#00b09b50")};
  }

  &:active {
    transform: translateY(0px);
  }
`;

const LabelHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
`;

const LabelTitle = styled.div`
  font-weight: 600;
  color: #2d3436;
  font-size: 0.95rem;
`;

const LabelDescription = styled.div`
  color: #636e72;
  font-size: 0.85rem;
  line-height: 1.4;
`;

const FooterContainer = styled.div`
  padding: 16px;
  background: linear-gradient(135deg, #f8f9fa, #e9ecef);
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  display: flex;
  justify-content: flex-end;
`;

const AddButtonWrapper = styled.div`
  button {
    background: linear-gradient(135deg, #00b09b, #96c93d) !important;
    color: white !important;
    border: none !important;
    padding: 10px 20px !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;

    &:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 176, 155, 0.2) !important;
    }

    &:active:not(:disabled) {
      transform: translateY(0px);
    }

    &:disabled {
      opacity: 0.7 !important;
      background: #e9ecef !important;
      color: #636e72 !important;
    }
  }
`;

interface DocTypePopupProps {
  labels: AnnotationLabelType[];
  onAdd: (label: AnnotationLabelType) => void;
}

export const DocTypePopup = ({ labels, onAdd }: DocTypePopupProps) => {
  const [selectedLabel, selectLabel] = useState<AnnotationLabelType>();
  const [searchString, setSearchString] = useState("");

  const labelFuse = new Fuse(labels, {
    threshold: 0.4,
    keys: ["text", "description"],
  });

  const filteredLabels =
    searchString === ""
      ? labels
      : labelFuse.search(searchString).map((item) => item.item);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchString(e.target.value);
  };

  return (
    <PopupContainer>
      <SearchContainer>
        <StyledInput
          placeholder="Search labels..."
          value={searchString}
          onChange={handleChange}
          icon={<Search size={16} style={{ color: "grey" }} />}
        />
      </SearchContainer>

      <LabelsContainer>
        {filteredLabels.length > 0 ? (
          filteredLabels.map((label) => (
            <LabelCard
              key={label.id}
              selected={Boolean(selectedLabel && selectedLabel.id === label.id)}
              onClick={() => selectLabel(label)}
            >
              <LabelHeader>
                <LabelTitle>{label.text}</LabelTitle>
                <Tag
                  size={16}
                  style={{
                    color: label.color || "#00b09b",
                    opacity: 0.8,
                  }}
                />
              </LabelHeader>
              {label.description && (
                <LabelDescription>{label.description}</LabelDescription>
              )}
            </LabelCard>
          ))
        ) : (
          <LabelCard selected={false}>
            <LabelHeader>
              <LabelTitle>No Matching Labels</LabelTitle>
              <SearchX size={16} style={{ color: "grey" }} />
            </LabelHeader>
            <LabelDescription>
              No labels match your search criteria. Try adjusting your search
              terms.
            </LabelDescription>
          </LabelCard>
        )}
      </LabelsContainer>

      <FooterContainer>
        <AddButtonWrapper>
          <Button
            disabled={!selectedLabel}
            onClick={selectedLabel ? () => onAdd(selectedLabel) : undefined}
          >
            Add Label
          </Button>
        </AddButtonWrapper>
      </FooterContainer>
    </PopupContainer>
  );
};
