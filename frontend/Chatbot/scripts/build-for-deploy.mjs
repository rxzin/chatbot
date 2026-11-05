// Builds the frontend and copies it to backend/app/frontend_build, where the FastAPI app
// serves it. Run this before every `fastapi deploy`, which doesn't build the frontend.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = resolve(frontendDir, "out");
const targetDir = resolve(frontendDir, "../../backend/app/frontend_build");

rmSync(outDir, { recursive: true, force: true });

const result = spawnSync("pnpm", ["exec", "next", "build"], {
  cwd: frontendDir,
  stdio: "inherit",
  shell: true,
  // Empty means same origin. It also overrides any URL in a local .env file.
  env: { ...process.env, NEXT_PUBLIC_API_URL: "" },
});
if (result.status !== 0) process.exit(result.status ?? 1);

if (!existsSync(resolve(outDir, "index.html"))) {
  console.error("Build finished but out/index.html is missing.");
  process.exit(1);
}

rmSync(targetDir, { recursive: true, force: true });
cpSync(outDir, targetDir, { recursive: true });
console.log(`Frontend copied to ${targetDir}`);
