import React, {
  useState,
  useMemo,
  useRef,
  useEffect,
  useCallback,
} from "react";
import { Form, Button } from "semantic-ui-react";
import Fuse from "fuse.js";
import styled from "styled-components";
import { AnalysisType, ExtractType } from "../../types/graphql-api";
import { AnalysisItem } from "./AnalysisItem";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import { ExtractItem } from "../extracts/ExtractItem";
import { X, Search } from "lucide-react";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../annotator/hooks/AnalysisHooks";
import { useAdditionalUIStates } from "../annotator/context/UISettingsAtom";
import { useCorpusState } from "../annotator/context/CorpusAtom";

const SelectorContainer = styled.div`
  height: 300px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-radius: 0.28571429rem;
  box-shadow: 0 1px 2px 0 rgba(34, 36, 38, 0.15);
  background: #fff;
`;

const MenuSection = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: flex-start;
  border-radius: 0px;
  height: 60px;
  padding: 1rem;
  background: #fff;
  border-bottom: 1px solid rgba(34, 36, 38, 0.15);
`;

const CardSection = styled.div`
  max-height: 240px;
  overflow: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-radius: 0px;
  padding: 1rem;
  background: #fff;
  position: relative;
`;

interface HorizontalSelectorForCorpusProps {
  read_only: boolean;
  analyses: AnalysisType[];
  extracts: ExtractType[];
}

export const ExtractAndAnalysisHorizontalSelector: React.FC<
  HorizontalSelectorForCorpusProps
> = ({ read_only, analyses, extracts }) => {
  const { width } = useWindowDimensions();
  const { selectedCorpus } = useCorpusState();
  const { selectedAnalysis, selectedExtract } = useAnalysisSelection();
  const { topbarVisible, setTopbarVisible } = useAdditionalUIStates();

  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const { onSelectAnalysis, onSelectExtract } = useAnalysisManager();

  const [searchTerm, setSearchTerm] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"analyses" | "extracts">(
    "analyses"
  );

  const fuseOptions = {
    keys: ["name", "description"], // Adjust these based on your data structure
    threshold: 0.4,
  };

  const analysesFuse = useMemo(
    () => new Fuse(analyses, fuseOptions),
    [analyses]
  );
  const extractsFuse = useMemo(
    () => new Fuse(extracts, fuseOptions),
    [extracts]
  );

  const filteredItems = useMemo(() => {
    if (!searchTerm) return activeTab === "analyses" ? analyses : extracts;

    const fuse = activeTab === "analyses" ? analysesFuse : extractsFuse;
    return fuse.search(searchTerm).map((result) => result.item);
  }, [activeTab, searchTerm, analyses, extracts, analysesFuse, extractsFuse]);

  const handleSearchChange = (value: string) => {
    setSearchTerm(value);
  };

  const mountedRef = useRef(false);

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
    }

    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    console.log("Topbar visibility changed:", {
      topbarVisible,
      isMobile: use_mobile_layout,
      shouldShowCloseButton: use_mobile_layout && topbarVisible,
    });
  }, [topbarVisible, use_mobile_layout]);

  const renderItems = useCallback(() => {
    if (filteredItems.length === 0) {
      return (
        <PlaceholderCard
          style={{
            padding: ".5em",
            margin: ".75em",
            minWidth: use_mobile_layout ? "250px" : "300px",
          }}
          key={`no_${activeTab}_available_placeholder`}
          title={`No ${
            activeTab.charAt(0).toUpperCase() + activeTab.slice(1)
          } Available...`}
          description={`If you have sufficient privileges, try creating a new ${
            activeTab === "analyses" ? "analysis" : "extract"
          } from the corpus page.`}
        />
      );
    }

    return filteredItems.map((item) =>
      activeTab === "analyses" ? (
        <AnalysisItem
          corpus={selectedCorpus}
          compact={use_mobile_layout}
          key={item.id}
          analysis={item as AnalysisType}
          selected={Boolean(
            selectedAnalysis && item.id === selectedAnalysis.id
          )}
          read_only={read_only}
          onSelect={() =>
            onSelectAnalysis(
              selectedAnalysis && item.id === selectedAnalysis.id
                ? null
                : (item as AnalysisType)
            )
          }
        />
      ) : (
        <ExtractItem
          corpus={selectedCorpus}
          compact={use_mobile_layout}
          key={item.id}
          extract={item as ExtractType}
          selected={Boolean(selectedExtract && item.id === selectedExtract.id)}
          read_only={read_only}
          onSelect={() =>
            onSelectExtract(
              selectedExtract && item.id === selectedExtract.id
                ? null
                : (item as ExtractType)
            )
          }
        />
      )
    );
  }, [
    filteredItems,
    use_mobile_layout,
    read_only,
    selectedAnalysis,
    selectedExtract,
    onSelectAnalysis,
    onSelectExtract,
  ]);

  return (
    <SelectorContainer id="HorizontalSelectorForCorpus">
      <MenuSection id="HorizontalSelectorForCorpus_Menu">
        <div style={{ marginRight: "10px" }}>
          <Button.Group>
            <Button
              active={activeTab === "analyses"}
              onClick={() => setActiveTab("analyses")}
            >
              Analyses
            </Button>
            <Button
              active={activeTab === "extracts"}
              onClick={() => setActiveTab("extracts")}
            >
              Extracts
            </Button>
          </Button.Group>
        </div>
        <div
          style={{
            width: use_mobile_layout ? "200px" : "50%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
          }}
        >
          <Form>
            <Form.Input
              icon={
                <i
                  className="icon"
                  onClick={searchTerm ? () => handleSearchChange("") : () => {}}
                  style={{
                    cursor: searchTerm ? "pointer" : "default",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {searchTerm ? <X size={16} /> : <Search size={16} />}
                </i>
              }
              placeholder={`Search for ${activeTab}...`}
              onChange={(e) => handleSearchChange(e.target.value)}
              value={searchTerm}
            />
          </Form>
        </div>
      </MenuSection>
      <CardSection id="HorizontalSelectorForCorpus_CardSegment">
        {use_mobile_layout && topbarVisible && (
          <div
            onClick={() => {
              console.log("Closing topbar");
              setTopbarVisible(false);
            }}
            style={{
              position: "absolute",
              bottom: "10px",
              right: "10px",
              cursor: "pointer",
              backgroundColor: "#DB2828",
              color: "#fff",
              borderRadius: "50%",
              width: "36px",
              height: "36px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 2px 5px rgba(0,0,0,0.3)",
              transition: "all 0.2s ease-in-out",
            }}
          >
            <X size={24} color="#333" />
          </div>
        )}
        <div
          id="HorizontalSelectorForCorpus_CardTrack"
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "row",
            justifyContent: "center",
            overflowX: "auto",
            flex: 1,
          }}
        >
          {mountedRef.current && renderItems()}
        </div>
      </CardSection>
    </SelectorContainer>
  );
};
