#!/usr/bin/env node
/**
 * Generate brand-correct PNG assets for the cite v3 rebrand:
 *
 *   - public/cite-192.png        (PWA "any" purpose, 192×192)
 *   - public/cite-512.png        (PWA "any" purpose, 512×512)
 *   - public/cite-maskable.png   (PWA "maskable" purpose, 512×512, with
 *                                 the mark inside the central ~80% safe
 *                                 area on the brand background colour)
 *   - public/OpenContractsScreenshot.png  (OG / Twitter card, 1200×630,
 *                                 wordmark + tagline on warm-paper bg —
 *                                 retains the legacy filename so the
 *                                 existing <meta og:image> reference
 *                                 keeps resolving)
 *
 * Uses Chromium via Playwright (already a dev dep for CT tests) instead
 * of pulling in librsvg / sharp / inkscape just for this one task.
 *
 * Run from the frontend/ directory:
 *
 *   node scripts/generate-brand-pngs.js
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const PUBLIC_DIR = path.resolve(__dirname, "..", "public");

// Cite brand palette — kept in lockstep with OS_LEGAL_COLORS in
// src/assets/configurations/osLegalStyles. Re-declared here as plain
// strings so the script (Node, no transpile) doesn't depend on the TS
// constants module.
const BRAND_COLORS = {
  ink: "#1E293B", // slate primary (bracket + headline)
  accent: "#0F766E", // teal accent (center node)
  paper: "#FAFAF7", // warm paper background
  textMuted: "#475569", // slate tagline copy
  metaMuted: "#64748B", // uppercase URL line on OG card
};

// Maskable icon spec: PWA shapes can crop ~20% off any edge, so the
// mark must live inside the central 80% safe area of a 512×512 frame.
// https://web.dev/maskable-icon/
const MASKABLE_FRAME = 512;
const MASKABLE_SAFE_AREA = Math.round(MASKABLE_FRAME * 0.8);

// Open Graph / Twitter card spec.
const OG_WIDTH = 1200;
const OG_HEIGHT = 630;

// Cite icon mark — matches frontend/public/favicon.svg and the inline
// geometry in src/components/brand/CiteMark.tsx. Re-declared here as
// a string template so the script doesn't depend on the React component
// at build time.
const citeMarkSvg = ({ size, strokeWidth }) => `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="${size}" height="${size}">
  <g transform="translate(32, 32)">
    <line x1="-19" y1="-20" x2="-19" y2="20" stroke="${BRAND_COLORS.ink}" stroke-width="${strokeWidth}"/>
    <line x1="-19" y1="-20" x2="-11" y2="-20" stroke="${BRAND_COLORS.ink}" stroke-width="${strokeWidth}"/>
    <line x1="-19" y1="20" x2="-11" y2="20" stroke="${BRAND_COLORS.ink}" stroke-width="${strokeWidth}"/>
    <line x1="19" y1="-20" x2="19" y2="20" stroke="${BRAND_COLORS.ink}" stroke-width="${strokeWidth}"/>
    <line x1="19" y1="-20" x2="11" y2="-20" stroke="${BRAND_COLORS.ink}" stroke-width="${strokeWidth}"/>
    <line x1="19" y1="20" x2="11" y2="20" stroke="${BRAND_COLORS.ink}" stroke-width="${strokeWidth}"/>
    <circle cx="0" cy="0" r="7" fill="${BRAND_COLORS.accent}"/>
  </g>
</svg>`;

// Renders an arbitrary HTML body inside Chromium at an exact viewport
// size and writes the captured PNG to disk.
async function snap(browser, { name, width, height, body, background }) {
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const html = `<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body {
    margin: 0;
    padding: 0;
    width: ${width}px;
    height: ${height}px;
    ${background ? `background: ${background};` : "background: transparent;"}
  }
  .stage {
    width: ${width}px;
    height: ${height}px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  body, .stage * {
    font-family: "Source Serif 4", "Source Serif Pro", Georgia, serif;
  }
</style></head>
<body><div class="stage">${body}</div></body></html>`;
  await page.setContent(html);

  const outPath = path.join(PUBLIC_DIR, name);
  await page.screenshot({
    path: outPath,
    omitBackground: !background,
    type: "png",
    clip: { x: 0, y: 0, width, height },
  });
  await context.close();
  console.log(
    `wrote ${path.relative(process.cwd(), outPath)} (${width}×${height})`
  );
}

async function main() {
  const browser = await chromium.launch();
  try {
    // ───────────────────────────────────────────────────────────────
    // PWA "any" icons — transparent background so the OS chrome /
    // launcher can place them on any surface.
    // ───────────────────────────────────────────────────────────────
    await snap(browser, {
      name: "cite-192.png",
      width: 192,
      height: 192,
      body: citeMarkSvg({ size: 192, strokeWidth: 2.4 }),
    });
    await snap(browser, {
      name: "cite-512.png",
      width: 512,
      height: 512,
      body: citeMarkSvg({ size: 512, strokeWidth: 2.4 }),
    });

    // ───────────────────────────────────────────────────────────────
    // PWA "maskable" icon — content lives inside the central safe area
    // (~80% of the frame) on a brand-coloured bezel so Android
    // adaptive-icon shapes don't crop into the mark.
    // ───────────────────────────────────────────────────────────────
    await snap(browser, {
      name: "cite-maskable.png",
      width: MASKABLE_FRAME,
      height: MASKABLE_FRAME,
      background: BRAND_COLORS.paper,
      body: `<div style="width: ${MASKABLE_SAFE_AREA}px; height: ${MASKABLE_SAFE_AREA}px;">${citeMarkSvg(
        {
          size: MASKABLE_SAFE_AREA,
          strokeWidth: 2.4,
        }
      )}</div>`,
    });

    // ───────────────────────────────────────────────────────────────
    // Open Graph / Twitter card — 1200×630, brand wordmark + the
    // public-record tagline. Keep the legacy filename so the existing
    // <meta og:image content="/OpenContractsScreenshot.png"> resolves
    // to the new cite-branded card without an index.html change.
    // ───────────────────────────────────────────────────────────────
    const ogBody = `
      <div style="
        width: ${OG_WIDTH}px;
        height: ${OG_HEIGHT}px;
        background: ${BRAND_COLORS.paper};
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 36px;
      ">
        <div style="display: flex; align-items: center; gap: 28px;">
          ${citeMarkSvg({ size: 140, strokeWidth: 2.4 })}
          <span style="
            font-family: 'Source Serif 4', 'Source Serif Pro', Georgia, serif;
            font-size: 140px;
            font-weight: 400;
            color: ${BRAND_COLORS.ink};
            letter-spacing: -3px;
            line-height: 1;
          ">[cite]</span>
        </div>
        <div style="
          font-family: 'Source Serif 4', 'Source Serif Pro', Georgia, serif;
          font-size: 36px;
          font-weight: 400;
          color: ${BRAND_COLORS.textMuted};
          letter-spacing: -0.5px;
          max-width: 900px;
          text-align: center;
          line-height: 1.35;
        ">
          The citation layer<br/>underneath the public record.
        </div>
        <div style="
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
          font-size: 16px;
          font-weight: 400;
          color: ${BRAND_COLORS.metaMuted};
          letter-spacing: 1.5px;
          text-transform: uppercase;
          margin-top: 12px;
        ">
          opensource.legal
        </div>
      </div>`;
    await snap(browser, {
      name: "OpenContractsScreenshot.png",
      width: OG_WIDTH,
      height: OG_HEIGHT,
      background: BRAND_COLORS.paper,
      body: ogBody,
    });
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
