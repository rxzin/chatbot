import { ImageResponse } from "next/og";
import { site } from "@/lib/site";

export const dynamic = "force-static";
export const alt = `${site.name} — ${site.tagline}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: 80,
        backgroundColor: "#09090b",
        color: "#f4f4f5",
        fontFamily: "sans-serif",
        backgroundImage:
          "radial-gradient(circle at 90% 10%, rgba(16, 185, 129, 0.22), transparent 50%),                radial-gradient(circle at 10% 90%, rgba(16, 185, 129, 0.1), transparent 45%)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 12,
            backgroundColor: "#10b981",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#000",
            fontWeight: 800,
            fontSize: 26,
          }}
        >
          ⚡
        </div>
        <span
          style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.02em" }}
        >
          {site.name}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div
          style={{
            fontSize: 64,
            fontWeight: 800,
            lineHeight: 1.1,
            letterSpacing: "-0.03em",
            maxWidth: 950,
          }}
        >
          Private AI chat that answers from your own documents.
        </div>
        <div style={{ fontSize: 28, color: "#a1a1aa", maxWidth: 800 }}>
          Ground answers with RAG, stream responses, and verify claims with
          inline citations.
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 22,
          color: "#10b981",
          fontWeight: 500,
        }}
      >
        <span>{new URL(site.url).host}</span>
        <span style={{ color: "#71717a" }}>
          Next.js · FastAPI · LangGraph · Pinecone
        </span>
      </div>
    </div>,
    { ...size },
  );
}
