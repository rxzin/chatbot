// Prints the chapter plan: bundles src/timeline.ts with esbuild and runs it.
const path = require("node:path");
const bundler = path.dirname(require.resolve("@remotion/bundler/package.json"));
const esbuild = require(require.resolve("esbuild", { paths: [bundler] }));
const out = esbuild.buildSync({ entryPoints: [path.join(__dirname, "..", "src", "timeline.ts")], bundle: true, write: false, format: "cjs", platform: "node" });
const m = { exports: {} };
new Function("module", "exports", "require", out.outputFiles[0].text)(m, m.exports, require);
const which = process.argv[2] === "full" ? "TIMELINE" : "HIGHLIGHTS_TIMELINE";
const { chapters, total } = m.exports[which];
const fps = m.exports.FPS;
for (const c of chapters) {
  const extra = c.kind === "footage" ? `segments ${c.segments.length} (sped ${c.segments.filter((s) => s.rate > 1).length}), zooms ${c.focuses.length}, captions ${c.captions.length}` : "scene";
  console.log(`${(c.from / fps).toFixed(1).padStart(6)}s  ${(c.duration / fps).toFixed(1).padStart(5)}s  ${c.title.padEnd(26)} ${extra}`);
}
console.log(`total ${(total / fps).toFixed(1)}s (${total} frames)`);
