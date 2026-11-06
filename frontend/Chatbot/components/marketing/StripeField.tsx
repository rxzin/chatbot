"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

const VERTEX = `
attribute vec2 aPosition;
void main() { gl_Position = vec4(aPosition, 0.0, 1.0); }
`;

// Thin vertical lines, brighter toward the top and bottom, each breathing slowly.
// Some lines carry a pulse of light that travels downward and leaves a short trail.
const FRAGMENT = `
precision mediump float;
uniform vec2 uResolution;
uniform float uTime;
uniform float uDpr;
uniform float uGap;
uniform float uStrength;
uniform vec3 uColor;

float hash(float n) { return fract(sin(n * 127.1) * 43758.5453); }

void main() {
  vec2 p = gl_FragCoord.xy / uDpr;
  vec2 size = uResolution / uDpr;
  float y = 1.0 - p.y / size.y;

  float offset = mod(size.x, uGap) * 0.5;
  float x = p.x - offset;
  float column = floor(x / uGap + 0.5);
  float distanceToLine = abs(x - column * uGap);
  float line = 1.0 - smoothstep(0.0, 0.85, distanceToLine);
  if (line <= 0.0) { gl_FragColor = vec4(0.0); return; }

  float seed = hash(column);
  float edges = pow(abs(y - 0.5) * 2.0, 1.4);
  float base = (0.17 + 0.33 * edges) * (0.7 + 0.3 * sin(uTime * 0.55 + seed * 6.2831));

  float speed = 0.05 + 0.07 * hash(column + 7.0);
  float head = fract(uTime * speed + seed);
  float behind = head - y;
  float trail = behind > 0.0 ? exp(-behind * 9.0) : 0.0;
  float pulse = trail * step(0.5, hash(column + 3.0));

  float alpha = clamp((base + pulse) * line * uStrength, 0.0, 1.0);
  gl_FragColor = vec4(uColor * alpha, alpha);
}
`;

function parseColor(value: string): [number, number, number] {
  const probe = document.createElement("canvas").getContext("2d");
  if (!probe) return [0.2, 0.83, 0.6];
  probe.fillStyle = value || "#34d399";
  const hex = probe.fillStyle;
  if (hex.startsWith("#")) {
    const n = parseInt(hex.slice(1), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
  }
  const rgb = hex.match(/[\d.]+/g)?.map(Number) ?? [52, 211, 153];
  return [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255];
}

function compile(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

type StripeFieldProps = {
  className?: string;
  /** Distance between lines, in CSS pixels. */
  gap?: number;
};

/**
 * A live WebGL field of vertical lines in the page's live color, faded out toward the
 * centre so the copy above it stays readable. It pauses off screen and in background
 * tabs, and draws a single still frame for people who prefer reduced motion.
 */
export function StripeField({ className, gap = 34 }: StripeFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { premultipliedAlpha: true, antialias: false });
    if (!gl) return;

    const vertex = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vertex || !fragment || !program) return;
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return;
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "aPosition");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const uniform = (name: string) => gl.getUniformLocation(program, name);
    const uResolution = uniform("uResolution");
    const uTime = uniform("uTime");
    const uDpr = uniform("uDpr");
    const uGap = uniform("uGap");
    const uStrength = uniform("uStrength");
    const uColor = uniform("uColor");

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let visible = true;
    const start = performance.now();

    const applyTheme = () => {
      const styles = getComputedStyle(canvas);
      gl.uniform3fv(uColor, parseColor(styles.getPropertyValue("--live").trim()));
      // Dark grounds need less line to read; light grounds need more.
      const dark = document.documentElement.classList.contains("dark");
      gl.uniform1f(uStrength, dark ? 0.9 : 0.75);
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uResolution, canvas.width, canvas.height);
      gl.uniform1f(uDpr, dpr);
      gl.uniform1f(uGap, gap);
    };

    const draw = (time: number) => {
      gl.uniform1f(uTime, time);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };

    const loop = () => {
      draw((performance.now() - start) / 1000);
      frame = requestAnimationFrame(loop);
    };

    const sync = () => {
      cancelAnimationFrame(frame);
      if (reduceMotion.matches) {
        draw(12);
      } else if (visible && document.visibilityState === "visible") {
        frame = requestAnimationFrame(loop);
      }
    };

    applyTheme();
    resize();
    sync();

    const resizeObserver = new ResizeObserver(() => {
      resize();
      if (reduceMotion.matches) draw(12);
    });
    resizeObserver.observe(canvas);

    const intersection = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    intersection.observe(canvas);

    const themeObserver = new MutationObserver(() => {
      applyTheme();
      if (reduceMotion.matches) draw(12);
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    document.addEventListener("visibilitychange", sync);
    reduceMotion.addEventListener("change", sync);

    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      intersection.disconnect();
      themeObserver.disconnect();
      document.removeEventListener("visibilitychange", sync);
      reduceMotion.removeEventListener("change", sync);
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
    };
  }, [gap]);

  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-0 [mask-image:radial-gradient(65%_55%_at_50%_48%,transparent_30%,black_100%)]",
        className,
      )}
    >
      <canvas ref={canvasRef} className="size-full" />
    </div>
  );
}
