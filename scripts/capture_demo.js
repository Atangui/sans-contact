// Records the README captures from the online demo (docs/index.html): an animated GIF of the
// guided tour and a few still images, written to docs/assets/demo/.
//
// Only the demo page is captured: synthetic hand, fictitious desktop, no camera (CLAUDE.md allows
// exactly this exception). The page runs on its own simulated clock (?capture=1), so every capture
// shows the same sequence. Intermediate frames go to a temporary folder outside the repository, deleted at the end.
//
// Development tool, not needed to run SansContact. Needs Node.js, Playwright with Chromium, and ffmpeg:
//   node scripts/capture_demo.js [--fps 15] [--width 1024]
"use strict";

const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const PAGE = path.join(ROOT, "docs", "index.html");
const OUT = path.join(ROOT, "docs", "assets", "demo");
const CAMERA_FPS = 30;
const VIEWPORT = { width: 1280, height: 720 };

// Still images: tour step (1-based) and seconds after the step started.
const STILLS = [
  { name: "accord.png", step: 2, after: 2.6 },
  { name: "prise-de-controle.png", step: 4, after: 1.0 },
  { name: "glisser-deposer.png", step: 9, after: 2.8 },
];

function option(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? Number(process.argv[i + 1]) : fallback;
}

async function main() {
  const fps = option("fps", 15);
  const width = option("width", 1024);
  const every = Math.round(CAMERA_FPS / fps);
  const frames = fs.mkdtempSync(path.join(os.tmpdir(), "sanscontact-demo-"));
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`file://${PAGE}?capture=1`);
    await page.waitForFunction(() => window.SansContactDemo !== undefined);

    const pending = [...STILLS];
    let stepStart = 0;
    let lastStep = 0;
    let count = 0;
    for (let frame = 0; ; frame++) {
      const info = await page.evaluate(() => {
        window.SansContactDemo.advance(1);
        return { t: window.SansContactDemo.t, step: window.SansContactDemo.step };
      });
      if (info.step < lastStep) break; // the tour has looped: one full pass recorded
      if (info.step !== lastStep) {
        lastStep = info.step;
        stepStart = info.t;
      }
      if (frame % every === 0) {
        await page.screenshot({ path: path.join(frames, `${String(count).padStart(5, "0")}.png`) });
        count += 1;
      }
      const still = pending.find((s) => s.step === info.step && info.t - stepStart >= s.after);
      if (still) {
        await page.screenshot({ path: path.join(OUT, still.name) });
        pending.splice(pending.indexOf(still), 1);
      }
    }
    if (errors.length) throw new Error(`errors in the page: ${errors.join("; ")}`);
    if (pending.length) throw new Error(`stills not taken: ${pending.map((s) => s.name).join(", ")}`);

    const gif = path.join(OUT, "demo.gif");
    execFileSync("ffmpeg", [
      "-y", "-loglevel", "error", "-framerate", String(fps), "-i", path.join(frames, "%05d.png"),
      "-vf", `scale=${width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];`
        + "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
      "-loop", "0", gif,
    ]);
    const size = (fs.statSync(gif).size / 1e6).toFixed(1);
    console.log(`${count} frames, ${(count / fps).toFixed(1)} s, ${size} MB -> ${path.relative(ROOT, gif)}`);
    for (const still of STILLS) console.log(`still -> ${path.relative(ROOT, path.join(OUT, still.name))}`);
  } finally {
    await browser.close();
    fs.rmSync(frames, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
