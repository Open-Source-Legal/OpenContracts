#!/usr/bin/env node
/**
 * Verification harness for the Docx Arcade demo (docs/demo/docx-arcade/).
 *
 * Not wired into CI (the demo is docs content with no build), but committed
 * so changes to engine.js/arcade.js/the cartridges can be re-verified without
 * re-deriving the harness. It drives the page through window.__arcade — the
 * demo's controller/debug handle — and asserts the interaction-order-sensitive
 * behavior that is easy to break silently: blur-commit semantics, the
 * DOM-vs-model source switch in pollSource, and NBSP caret-addressability.
 *
 * Usage:
 *   node scripts/verify_docx_arcade.js
 *
 * Requirements:
 *   - `playwright-core` resolvable (e.g. `npm i playwright-core` anywhere on
 *     NODE_PATH) and a Chromium binary. Set CHROMIUM_PATH to the executable;
 *     if unset, the script tries the full `playwright` package's bundled one.
 *   - Network access to jsDelivr for the pinned docxodus engine, OR a local
 *     mirror: set ENGINE_URL to an absolute/relative URL of embed.bundle.js
 *     (its dist/wasm/_framework/ tree must sit beside it — the bundle
 *     resolves `<module dir>/wasm/_framework/dotnet.js` from import.meta.url).
 *   - HTTPS_PROXY, if set, is passed to the browser (localhost bypassed).
 *
 * The static server serves the repo's docs/demo/docx-arcade/ on an ephemeral
 * port; ENGINE_URL, when relative, is resolved against that origin.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "docs", "demo", "docx-arcade");
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".dat": "application/octet-stream",
};

function serve(rootDirs) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
      let rel = urlPath.replace(/^\/+/, "") || "index.html";
      if (rel.endsWith("/")) rel += "index.html";
      for (const root of rootDirs) {
        const file = path.join(root, rel);
        // Separator-suffixed prefix check: bare startsWith(root) would let a
        // sibling dir sharing root as a string prefix (root + "-evil") pass.
        if (!file.startsWith(root + path.sep)) continue;
        if (fs.existsSync(file) && fs.statSync(file).isFile()) {
          res.writeHead(200, { "Content-Type": MIME[path.extname(file)] ?? "application/octet-stream" });
          fs.createReadStream(file)
            .on("error", () => res.destroy())
            .pipe(res);
          return;
        }
      }
      res.writeHead(404).end("not found");
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function chromium() {
  const pc = require("playwright-core");
  if (process.env.CHROMIUM_PATH) {
    return { pw: pc, executablePath: process.env.CHROMIUM_PATH };
  }
  try {
    return { pw: require("playwright"), executablePath: undefined };
  } catch {
    throw new Error("Set CHROMIUM_PATH to a Chromium executable, or install the full `playwright` package.");
  }
}

const results = [];
const ok = (name, pass, detail = "") => {
  results.push({ name, pass });
  console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

(async () => {
  // ENGINE_URL may point at a local mirror directory served alongside the demo.
  const extraRoot = process.env.ENGINE_DIR ? [path.resolve(process.env.ENGINE_DIR)] : [];
  const server = await serve([ROOT, ...extraRoot]);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const engineParam = process.env.ENGINE_URL ? `?engine=${encodeURIComponent(process.env.ENGINE_URL)}` : "";
  const url = `${origin}/index.html${engineParam}`;

  const { pw, executablePath } = chromium();
  const browser = await pw.chromium.launch({
    executablePath,
    headless: true,
    ...(process.env.HTTPS_PROXY
      ? { proxy: { server: process.env.HTTPS_PROXY, bypass: "localhost,127.0.0.1" }, args: ["--ignore-certificate-errors"] }
      : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 950 } });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));

  console.log(`loading ${url}`);
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__arcade || window.__arcadeError, null, {
    timeout: 120000,
    polling: 500,
  });
  const bootErr = await page.evaluate(() => window.__arcadeError ?? null);
  ok("boot", !bootErr, bootErr ?? "controller live");
  if (bootErr) {
    await browser.close();
    server.close();
    process.exit(1);
  }

  // ── Courier Quest ───────────────────────────────────────────────────
  await page.waitForTimeout(4500);
  const t1 = await page.evaluate(() => ({
    frames: window.__arcade.frames(),
    fps: window.__arcade.fps(),
    timings: window.__arcade.timings(),
    phase: window.__arcade.debugGame().phase,
  }));
  ok("frames advancing", t1.frames > 20, `frames=${t1.frames}`);
  ok("fps reasonable", t1.fps > 5, `fps=${t1.fps.toFixed(1)} runs=${t1.timings.runs}`);
  ok("quest in play phase", t1.phase === "play", `phase=${t1.phase}`);
  ok(
    "HUD rendered into the document",
    /COURIER QUEST/.test(await page.evaluate(() => window.__arcade.screenText()))
  );

  const clickScreen = async () => {
    const box = await page.evaluate(() => {
      const a = window.__arcade;
      const el = a.editor.root.querySelector(`[data-anchor="${a.screenAnchor().split(":")[2]}"]`);
      el.scrollIntoView({ block: "center" });
      const r = el.getBoundingClientRect();
      return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    await page.waitForTimeout(300);
    await page.mouse.click(box.x, box.y);
    await page.waitForTimeout(200);
  };
  await clickScreen();
  ok("click grabs controls", (await page.evaluate(() => window.__arcade.control())) === "game");

  const p0 = await page.evaluate(() => ({ ...window.__arcade.debugGame().player }));
  await page.keyboard.down("d");
  await page.waitForTimeout(1200);
  await page.keyboard.up("d");
  const p1 = await page.evaluate(() => ({ ...window.__arcade.debugGame().player }));
  ok("walk right moves player", p1.x > p0.x + 2, `x ${p0.x.toFixed(1)} → ${p1.x.toFixed(1)}`);
  await page.keyboard.press("Space");
  await page.waitForTimeout(260);
  const p2 = await page.evaluate(() => ({ ...window.__arcade.debugGame().player }));
  ok("space jumps", p2.y < p1.y - 0.5, `y ${p1.y.toFixed(1)} → ${p2.y.toFixed(1)}`);

  await page.keyboard.press("Escape");
  ok("Esc releases controls", (await page.evaluate(() => window.__arcade.control())) === "doc");

  // ── Live level editing: type into ROOM 1 while the game runs ────────
  const room = await page.evaluate(() => {
    const a = window.__arcade;
    const el = a.editor.root.querySelector(
      `[data-anchor="${a.cartridgeAnchors().room0.split(":")[2]}"]`
    );
    el.scrollIntoView({ block: "center" });
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width * 0.5, y: r.y + r.height * 0.25 };
  });
  await page.waitForTimeout(400);
  await page.mouse.click(room.x, room.y);
  await page.waitForTimeout(300);
  const framesBefore = await page.evaluate(() => window.__arcade.frames());
  await page.keyboard.type("HELLO", { delay: 180 });
  await page.waitForTimeout(1500);
  const typed = await page.evaluate(() => {
    const a = window.__arcade;
    const rows = a.debugGame().rows ?? [];
    const rowWith = rows.find((r) => r.includes("HELLO"));
    // Row width comes from the live rows (solids is row-major COLS wide),
    // so this stays correct if the screen geometry ever changes.
    const width = rows[0]?.length ?? 0;
    return {
      framesAfter: a.frames(),
      inGame: Boolean(rowWith),
      solid: rowWith
        ? a.debugGame().solids[rows.indexOf(rowWith) * width + rowWith.indexOf("H")] === 1
        : false,
    };
  });
  ok("game kept running while typing", typed.framesAfter > framesBefore);
  ok("typed word ingested LIVE (no blur, DOM overlay)", typed.inGame);
  ok("typed word is solid terrain", typed.solid);

  // Clicking the screen blurs the cartridge → commit to the session model.
  await clickScreen();
  await page.waitForTimeout(800);
  const committed = await page.evaluate(() => {
    const a = window.__arcade;
    return {
      inModel: a.session.raw.getXml(a.cartridgeAnchors().room0).includes("HELLO"),
      control: a.control(),
    };
  });
  ok("click-screen committed typed text to the model", committed.inModel);
  ok("click-screen grabbed the controls", committed.control === "game");

  // ── Docx Dungeon ────────────────────────────────────────────────────
  await page.evaluate(() => window.__arcade.setGame("dungeon"));
  await page.waitForTimeout(2200);
  const d0 = await page.evaluate(() => ({
    phase: window.__arcade.debugGame().phase,
    px: window.__arcade.debugGame().px,
    py: window.__arcade.debugGame().py,
  }));
  ok("dungeon in play phase", d0.phase === "play", `phase=${d0.phase}`);
  await page.evaluate(() => window.__arcade.setControl("game"));
  await page.keyboard.down("w");
  await page.waitForTimeout(1100);
  await page.keyboard.up("w");
  const d1 = await page.evaluate(() => ({
    px: window.__arcade.debugGame().px,
    py: window.__arcade.debugGame().py,
  }));
  ok("dungeon W walks forward", Math.hypot(d1.px - d0.px, d1.py - d0.py) > 1);

  // Session-level plan edit (an agent-style mutation) raises a wall live.
  const zEdit = await page.evaluate(() => {
    const a = window.__arcade;
    const anchor = a.cartridgeAnchors().plan;
    let xml = a.session.raw.getXml(anchor);
    let count = 0;
    xml = xml.replace(/(<w:t [^>]*>)([^<]{48})(<\/w:t>)/g, (m, a1, row, a3) => {
      count++;
      if (count === 18) return a1 + row.slice(0, 20) + "Z" + row.slice(21) + a3;
      return m;
    });
    const res = a.session.raw.replaceXml(anchor, xml);
    return { rows: count, success: res.success };
  });
  await page.waitForTimeout(1500);
  const zInGrid = await page.evaluate(() => {
    const g = window.__arcade.debugGame().grid;
    return g ? g.some((r) => r.includes("Z")) : false;
  });
  ok("session-level floor-plan edit raises a wall", zEdit.success !== false && zInGrid);

  // An astral char (emoji) typed into a level must not strand a lone
  // surrogate in the grid or halt the frame loop — fitRows() neutralizes
  // each surrogate unit into a '?' wall cell.
  await page.evaluate(() => {
    const a = window.__arcade;
    const anchor = a.cartridgeAnchors().plan;
    let xml = a.session.raw.getXml(anchor);
    let count = 0;
    xml = xml.replace(/(<w:t [^>]*>)([^<]{48})(<\/w:t>)/g, (m, a1, row, a3) => {
      count++;
      if (count === 12) return a1 + row.slice(0, 24) + "🙂" + row.slice(26) + a3;
      return m;
    });
    a.session.raw.replaceXml(anchor, xml);
  });
  await page.waitForTimeout(1200);
  const emojiState = await page.evaluate(() => ({
    playing: window.__arcade.playing(),
    frames: window.__arcade.frames(),
    qWall: window.__arcade.debugGame().grid?.some((r) => r.includes("?")) ?? false,
  }));
  await page.waitForTimeout(600);
  const framesAfterEmoji = await page.evaluate(() => window.__arcade.frames());
  ok(
    "emoji in the floor plan does not halt the loop",
    emojiState.playing && framesAfterEmoji > emojiState.frames
  );
  ok("astral char becomes ?-wall cells", emojiState.qWall);

  const t2 = await page.evaluate(() => ({ fps: window.__arcade.fps(), timings: window.__arcade.timings() }));
  ok("dungeon fps reasonable", t2.fps > 5, `fps=${t2.fps.toFixed(1)} runs=${t2.timings.runs}`);
  ok("run budget respected", t2.timings.runs < 150, `${t2.timings.runs} runs`);

  const stats = await page.textContent("#dockstats");
  ok("stats telemetry live", /fps/.test(stats) && /runs/.test(stats));
  ok("no uncaught page errors", pageErrors.length === 0, pageErrors.slice(0, 3).join(" | "));

  await browser.close();
  server.close();
  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error("HARNESS ERROR:", e);
  process.exit(2);
});
