// Cuts out/chat-demo.mp4 into one clip per chapter, using the same timeline as the video.
// Run after rendering: node scripts/split-chapters.cjs
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { mkdirSync } = require("node:fs");

const root = path.join(__dirname, "..");
const bundler = path.dirname(require.resolve("@remotion/bundler/package.json"));
const esbuild = require(require.resolve("esbuild", { paths: [bundler] }));
const built = esbuild.buildSync({
  entryPoints: [path.join(root, "src", "timeline.ts")],
  bundle: true,
  write: false,
  format: "cjs",
  platform: "node",
});
const m = { exports: {} };
new Function("module", "exports", "require", built.outputFiles[0].text)(m, m.exports, require);
const { chapters } = m.exports.TIMELINE;
const fps = m.exports.FPS;

const outDir = path.join(root, "out", "chapters");
mkdirSync(outDir, { recursive: true });
const input = path.join(root, "out", "chat-demo.mp4");

chapters.forEach((c, i) => {
  const name = `${String(i + 1).padStart(2, "0")}-${c.id}.mp4`;
  const args = [
    "exec", "remotion", "ffmpeg", "-y", "-v", "error",
    "-ss", (c.from / fps).toFixed(3), "-i", input,
    "-t", (c.duration / fps).toFixed(3),
    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-an",
    path.join(outDir, name),
  ];
  const r = spawnSync("pnpm", args, { cwd: root, shell: true, stdio: "inherit" });
  console.log(r.status === 0 ? `ok  ${name}` : `FAIL ${name}`);
});
