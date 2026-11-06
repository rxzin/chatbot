import { loadFont as loadGeist } from "@remotion/google-fonts/Geist";
import { loadFont as loadUrbanist } from "@remotion/google-fonts/Urbanist";

// The app's own palette (DESIGN.md): zinc neutrals and one emerald for live things.
export const C = {
  bg: "#000000",
  card: "#09090b",
  raised: "#18181b",
  line: "#27272a",
  muted: "#a1a1aa",
  fg: "#ffffff",
  live: "#34d399",
};

export const display = loadUrbanist("normal", { weights: ["500", "600"] }).fontFamily;
export const body = loadGeist("normal", { weights: ["300", "400", "500"] }).fontFamily;
