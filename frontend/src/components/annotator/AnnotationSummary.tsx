import { Card, CardBody, Chip } from "@os-legal/ui";
import styled from "styled-components";
import _ from "lodash";
import { TruncatedText } from "../widgets/data-display/TruncatedText";
import { ServerTokenAnnotation } from "./types/annotations";
import { usePages } from "./context/DocumentAtom";
import { usePdfAnnotations } from "./hooks/AnnotationHooks";

const CardHeader = styled.div`
  font-weight: 600;
  font-size: 1.1rem;
  margin-bottom: 0.5rem;
`;

const CardDescription = styled.div`
  color: #333;
`;

interface AnnotationSummaryProps {
  annotationId: string;
}

export const AnnotationSummary = ({ annotationId }: AnnotationSummaryProps) => {
  // console.log("AnnotationSummary received ID:", annotationId);

  const { pages } = usePages();
  const { pdfAnnotations } = usePdfAnnotations();

  const this_annotation = _.find(pdfAnnotations.annotations, {
    id: annotationId,
  }) as ServerTokenAnnotation;

  if (!this_annotation) {
    console.warn(
      `AnnotationSummary: Annotation with ID ${annotationId} not found in context.`
    );
    return (
      <Card style={{ width: "50vw", border: "1px dashed red" }}>
        <CardBody>
          <CardHeader>Annotation Not Found</CardHeader>
          <CardDescription>ID: {annotationId}</CardDescription>
        </CardBody>
      </Card>
    );
  }

  if (!pages) {
    return null;
  }

  const pageInfo = pages[this_annotation.page];

  const text = this_annotation.rawText;

  return (
    <Card style={{ width: "50vw" }}>
      <CardBody>
        <CardHeader>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              flexDirection: "row",
            }}
          >
            <Chip
              size="sm"
              style={{
                backgroundColor: this_annotation?.annotationLabel?.color
                  ? this_annotation.annotationLabel.color
                  : "gray",
                color: "white",
              }}
            >
              {this_annotation?.annotationLabel?.text
                ? this_annotation.annotationLabel.text
                : ""}
            </Chip>
            <div>
              <b>
                Page{" "}
                {pageInfo?.page?.pageNumber ? pageInfo.page.pageNumber : "-"}
              </b>
            </div>
          </div>
        </CardHeader>
        <CardDescription>
          <TruncatedText text={text} limit={128} />
        </CardDescription>
      </CardBody>
    </Card>
  );
};
