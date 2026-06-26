/**
 * ArtifactPosterRoute — the public ``/a/<slug>`` page for a shareable corpus
 * poster (Artifact).
 *
 * Resolves the artifact by slug (corpus-as-gate on the backend, so a public
 * corpus's poster is anonymous-viewable), renders the named template full-bleed
 * on a fixed poster canvas using the artifact's *configurable* captions, and
 * offers share affordances (Download PNG, Copy link). The template itself is
 * corpus-agnostic — it reads its own data from the artifact's ``corpusId``.
 */
import React, { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { Download, Link2 } from "lucide-react";
import { toast } from "react-toastify";

import {
  GET_ARTIFACT_BY_SLUG,
  GetArtifactBySlugInput,
  GetArtifactBySlugOutput,
  ArtifactNode,
} from "../../graphql/queries";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import { SpendingBeeswarm } from "../corpuses/CorpusHome/intelligence/SpendingBeeswarm";

// Poster template registry — maps an ``artifact.template`` id to its renderer.
// Adding a template (e.g. "reference-web") is a one-line entry here; the model
// stores the id as a free string, so no migration is needed.
const POSTER_TEMPLATES: Record<string, (a: ArtifactNode) => JSX.Element> = {
  "spending-beeswarm": (a) => (
    <SpendingBeeswarm
      corpusId={a.corpusId}
      title={a.title || undefined}
      takeaway={a.subtitle || undefined}
      byline={a.byline || undefined}
      noun={
        (a.config && typeof a.config.noun === "string"
          ? (a.config.noun as string)
          : undefined) || undefined
      }
    />
  ),
};

const Page = styled.div`
  min-height: 100vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  padding: 1.25rem 1rem 4rem;
  box-sizing: border-box;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
`;

const Toolbar = styled.div`
  width: 100%;
  max-width: 1200px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
`;

const ToolbarTitle = styled.div`
  font-size: 0.95rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const Actions = styled.div`
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
`;

const Btn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.9rem;
  border-radius: 9999px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
  svg {
    width: 15px;
    height: 15px;
  }
`;

const PosterFrame = styled.div`
  width: 100%;
  max-width: 1200px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
  overflow: hidden;
`;

const Centered = styled.div`
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.95rem;
`;

/** Rasterise the poster's SVG to a 2× PNG and trigger a download. */
async function downloadPosterPng(root: HTMLElement | null, filename: string) {
  const svg = root?.querySelector("svg");
  if (!svg) {
    toast.error("Nothing to export yet.");
    return;
  }
  const xml = new XMLSerializer().serializeToString(svg);
  const vb = svg.viewBox.baseVal;
  const w = vb && vb.width ? vb.width : svg.clientWidth || 1200;
  const h = vb && vb.height ? vb.height : svg.clientHeight || 660;
  const scale = 2;
  const svg64 =
    "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("svg load failed"));
    img.src = svg64;
  });
  const canvas = document.createElement("canvas");
  canvas.width = w * scale;
  canvas.height = h * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, "image/png");
}

export const ArtifactPosterRoute: React.FC = () => {
  const { slug = "" } = useParams<{ slug: string }>();
  const posterRef = useRef<HTMLDivElement>(null);

  const { data, loading } = useQuery<
    GetArtifactBySlugOutput,
    GetArtifactBySlugInput
  >(GET_ARTIFACT_BY_SLUG, {
    variables: { slug },
    errorPolicy: "all",
    fetchPolicy: "cache-and-network",
  });

  const artifact = data?.artifactBySlug ?? null;

  useEffect(() => {
    if (artifact?.title) document.title = `${artifact.title} · OpenContracts`;
  }, [artifact?.title]);

  const renderTemplate = artifact ? POSTER_TEMPLATES[artifact.template] : null;

  if (loading && !artifact) {
    return (
      <Page>
        <Centered>Loading poster…</Centered>
      </Page>
    );
  }
  if (!artifact || !renderTemplate) {
    return (
      <Page>
        <Centered data-testid="artifact-not-found">
          This artifact isn't available.
        </Centered>
      </Page>
    );
  }

  return (
    <Page>
      <Toolbar>
        <ToolbarTitle>{artifact.title || "Corpus poster"}</ToolbarTitle>
        <Actions>
          <Btn
            onClick={() =>
              downloadPosterPng(posterRef.current, `${artifact.slug}.png`)
            }
            data-testid="artifact-download"
          >
            <Download />
            PNG
          </Btn>
          <Btn
            onClick={() => {
              navigator.clipboard?.writeText(window.location.href);
              toast.success("Link copied");
            }}
            data-testid="artifact-copy-link"
          >
            <Link2 />
            Copy link
          </Btn>
        </Actions>
      </Toolbar>

      <PosterFrame ref={posterRef} data-testid="artifact-poster">
        {renderTemplate(artifact)}
      </PosterFrame>
    </Page>
  );
};
