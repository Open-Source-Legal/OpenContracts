/**
 * The DOCX viewer: `@os-legal/react-contract-annotate`'s `DocxAnnotator` on
 * the bytes and parser text OpenContracts has loaded (`useDocumentLoader`),
 * bound to OpenContracts' state by `useViewerBindings`. Annotation offsets
 * index into `docText`, the text the server's parser produced.
 */
import React, { useMemo } from "react";
import { DocxAnnotator } from "@os-legal/react-contract-annotate/docx";

import {
  DOCXODUS_WASM_BUILD_DIR,
  DOCXODUS_WASM_DEV_PATH,
} from "../../../../assets/configurations/constants";
import { useViewerBindings } from "../../bindings/useViewerBindings";
import { ViewerFrame } from "../../bindings/ViewerFrame";
import { useDocText, useDocxBytes } from "../../context/DocumentAtom";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../../types/annotations";

/** Where `frontend/tooling/docxodusWasm.ts` serves the WebAssembly runtime. */
const DOCXODUS_WASM_BASE_URL = import.meta.env.PROD
  ? `${import.meta.env.BASE_URL}${DOCXODUS_WASM_BUILD_DIR}`
  : DOCXODUS_WASM_DEV_PATH;

interface DocxAnnotatorWrapperProps {
  readOnly: boolean;
  createAnnotation: (
    annotation: ServerTokenAnnotation | ServerSpanAnnotation
  ) => Promise<void>;
}

const DocxAnnotatorWrapper: React.FC<DocxAnnotatorWrapperProps> = ({
  readOnly,
  createAnnotation,
}) => {
  const { docText } = useDocText();
  const { docxBytes } = useDocxBytes();

  const { props, handleRef, dialogs } = useViewerBindings({
    format: "docx",
    readOnly,
    createAnnotation,
  });

  const source = useMemo(
    () => (docxBytes && docxBytes.length > 0 ? { data: docxBytes } : null),
    [docxBytes]
  );

  if (!source) {
    return (
      <div
        data-testid="docx-annotator-wrapper-loading"
        style={{ padding: "1rem", textAlign: "center" }}
      >
        Loading DOCX data...
      </div>
    );
  }

  return (
    <ViewerFrame data-testid="docx-annotator">
      <DocxAnnotator
        ref={handleRef}
        source={source}
        text={docText}
        wasmBaseUrl={DOCXODUS_WASM_BASE_URL}
        {...props}
      />
      {dialogs}
    </ViewerFrame>
  );
};

export default React.memo(DocxAnnotatorWrapper);
