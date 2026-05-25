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

// Cite icon mark — matches frontend/public/favicon.svg and the inline
// geometry in src/components/brand/CiteMark.tsx. Re-declared here as
// a string template so the script doesn't depend on the React component
// at build time.
const citeMarkSvg = ({ size, strokeWidth }) => `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="${size}" height="${size}">
  <g transform="translate(32, 32)">
    <line x1="-19" y1="-20" x2="-19" y2="20" stroke="#1E293B" stroke-width="${strokeWidth}"/>
    <line x1="-19" y1="-20" x2="-11" y2="-20" stroke="#1E293B" stroke-width="${strokeWidth}"/>
    <line x1="-19" y1="20" x2="-11" y2="20" stroke="#1E293B" stroke-width="${strokeWidth}"/>
    <line x1="19" y1="-20" x2="19" y2="20" stroke="#1E293B" stroke-width="${strokeWidth}"/>
    <line x1="19" y1="-20" x2="11" y2="-20" stroke="#1E293B" stroke-width="${strokeWidth}"/>
    <line x1="19" y1="20" x2="11" y2="20" stroke="#1E293B" stroke-width="${strokeWidth}"/>
    <circle cx="0" cy="0" r="7" fill="#0F766E"/>
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
    // PWA "maskable" icon — content lives inside the central 80%
    // (≈ 410px at 512px) safe area on a brand-coloured bezel so
    // Android adaptive-icon shapes don't crop into the mark.
    // ───────────────────────────────────────────────────────────────
    const SAFE = 410;
    await snap(browser, {
      name: "cite-maskable.png",
      width: 512,
      height: 512,
      background: "#FAFAF7",
      body: `<div style="width: ${SAFE}px; height: ${SAFE}px;">${citeMarkSvg({
        size: SAFE,
        strokeWidth: 2.4,
      })}</div>`,
    });

    // ───────────────────────────────────────────────────────────────
    // Open Graph / Twitter card — 1200×630, brand wordmark + the
    // public-record tagline. Keep the legacy filename so the existing
    // <meta og:image content="/OpenContractsScreenshot.png"> resolves
    // to the new cite-branded card without an index.html change.
    // ───────────────────────────────────────────────────────────────
    const ogBody = `
      <div style="
        width: 1200px;
        height: 630px;
        background: #FAFAF7;
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
            color: #1E293B;
            letter-spacing: -3px;
            line-height: 1;
          ">[cite]</span>
        </div>
        <div style="
          font-family: 'Source Serif 4', 'Source Serif Pro', Georgia, serif;
          font-size: 36px;
          font-weight: 400;
          color: #475569;
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
          color: #64748B;
          letter-spacing: 1.5px;
          text-transform: uppercase;
          margin-top: 12px;
        ">
          opensource.legal
        </div>
      </div>`;
    await snap(browser, {
      name: "OpenContractsScreenshot.png",
      width: 1200,
      height: 630,
      background: "#FAFAF7",
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
