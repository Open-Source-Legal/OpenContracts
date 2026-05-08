import React from "react";
import { FetchMoreFooter } from "../src/components/widgets/infinite_scroll/FetchMoreFooter";

interface HarnessProps {
  visible: boolean;
  message?: string;
  "data-testid"?: string;
}

/** Test harness mirroring how FetchMoreFooter renders at the bottom of an infinite-scroll list. */
export const FetchMoreFooterHarness: React.FC<HarnessProps> = ({
  visible,
  message = "Loading more documents…",
  "data-testid": dataTestId,
}) => {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "#ffffff",
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        padding: "0 0 80px",
      }}
      data-testid="harness-root"
    >
      <FetchMoreFooter
        visible={visible}
        message={message}
        data-testid={dataTestId}
      />
    </div>
  );
};
