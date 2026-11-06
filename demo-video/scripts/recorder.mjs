// Records the demo footage from the live site with Playwright, plus a timeline per take.
// Usage: node recorder.mjs <take> [<take> ...]   takes: landing, user, admin, mobile
import { chromium } from "playwright";
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "public", "footage");
mkdirSync(OUT, { recursive: true });
const env = Object.fromEntries(
  readFileSync(join(HERE, "..", "demo.env"), "utf8").split(/\r?\n/).filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]),
);
const SITE = env.SITE;
const PDF = join(HERE, "..", "northwind-handbook.pdf");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- Page staging: a visible cursor with a click ripple, and no spoken voice prompt -----
const stage = () => {
  // The voice question is audio only; recordings can't play it, so skip it.
  try {
    Object.defineProperty(Navigator.prototype, "userActivation", {
      get: () => ({ hasBeenActive: false, isActive: false }),
      configurable: true,
    });
  } catch {}
  const install = () => {
    if (document.getElementById("__demo_cursor")) return;
    const c = document.createElement("div");
    c.id = "__demo_cursor";
    c.innerHTML =
      '<svg width="28" height="28" viewBox="0 0 24 24"><path d="M5 2.5l14 8.2-6.2 1.6-3 6.2z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, {
      position: "fixed", left: "0", top: "0", zIndex: "2147483647", pointerEvents: "none",
      transform: "translate(-200px,-200px)", filter: "drop-shadow(0 1px 2px rgba(0,0,0,.45))",
    });
    document.documentElement.appendChild(c);
    const pos = window.__demoPos || { x: -200, y: -200 };
    c.style.transform = `translate(${pos.x - 4}px,${pos.y - 2}px)`;
    document.addEventListener("mousemove", (e) => {
      window.__demoPos = { x: e.clientX, y: e.clientY };
      c.style.transform = `translate(${e.clientX - 4}px,${e.clientY - 2}px)`;
    }, true);
    document.addEventListener("mousedown", (e) => {
      const r = document.createElement("div");
      Object.assign(r.style, {
        position: "fixed", left: `${e.clientX - 18}px`, top: `${e.clientY - 18}px`, width: "36px", height: "36px",
        borderRadius: "50%", border: "2px solid #34d399", zIndex: "2147483646", pointerEvents: "none",
        transition: "transform .45s ease-out, opacity .45s ease-out", transform: "scale(.4)", opacity: "1",
      });
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = "scale(1.4)"; r.style.opacity = "0"; });
      setTimeout(() => r.remove(), 500);
    }, true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install);
  else install();
};

class Take {
  constructor(name, viewport) {
    this.name = name;
    this.viewport = viewport;
    this.events = [];
    this.pos = { x: viewport.width / 2, y: viewport.height / 2 };
  }
  async open(browser, { theme = "dark", dpr = 1 } = {}) {
    this.ctx = await browser.newContext({
      viewport: this.viewport,
      deviceScaleFactor: dpr,
      recordVideo: { dir: OUT, size: this.viewport },
    });
    await this.ctx.addInitScript((t) => {
      if (!sessionStorage.getItem("__seeded")) {
        localStorage.setItem("theme", t);
        sessionStorage.setItem("__seeded", "1");
      }
    }, theme);
    await this.ctx.addInitScript(stage);
    this.page = await this.ctx.newPage();
    this.t0 = Date.now();
    return this.page;
  }
  t() { return +((Date.now() - this.t0) / 1000).toFixed(2); }
  mark(type, data = {}) { this.events.push({ t: this.t(), type, ...data }); }
  chapter(id, title, caption) { this.mark("chapter", { id, title, caption }); }
  caption(text) { this.mark("caption", { text }); }
  async box(locator) {
    const b = await locator.boundingBox().catch(() => null);
    return b ? { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) } : null;
  }
  async focus(locator, label, seconds = 2.5) {
    const b = await this.box(locator);
    if (b) this.mark("focus", { label, box: b, duration: seconds });
  }
  async glide(x, y, steps = 28) {
    await this.page.mouse.move(x, y, { steps });
    this.pos = { x, y };
  }
  async moveTo(locator, { steps = 28, dx = 0.5, dy = 0.5 } = {}) {
    await locator.scrollIntoViewIfNeeded().catch(() => {});
    const b = await locator.boundingBox();
    if (!b) throw new Error(`no box for ${locator}`);
    await this.glide(b.x + b.width * dx, b.y + b.height * dy, steps);
    return b;
  }
  async click(locator, opts = {}) {
    const b = await this.moveTo(locator, opts);
    this.mark("click", { box: { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) } });
    await sleep(180);
    await this.page.mouse.down();
    await sleep(70);
    await this.page.mouse.up();
  }
  async type(locator, text, delay = 38) {
    await this.click(locator);
    await locator.pressSequentially(text, { delay });
  }
  async restoreCursor() {
    // A new document draws the cursor off-screen until it moves; nudge it back.
    await this.page.mouse.move(this.pos.x + 1, this.pos.y + 1);
    await this.page.mouse.move(this.pos.x, this.pos.y);
  }
  async goto(path) {
    await this.page.goto(SITE + path, { waitUntil: "domcontentloaded" });
    await this.page.waitForLoadState("load").catch(() => {});
    await this.restoreCursor();
  }
  async wheel(total, step = 120, pause = 70) {
    const n = Math.ceil(Math.abs(total) / step);
    for (let i = 0; i < n; i++) {
      await this.page.mouse.wheel(0, Math.sign(total) * step);
      await sleep(pause);
    }
  }
  async close() {
    const video = this.page.video();
    await this.ctx.close();
    const src = await video.path();
    const dst = join(OUT, `${this.name}.webm`);
    renameSync(src, dst);
    writeFileSync(join(OUT, `${this.name}.json`), JSON.stringify({ name: this.name, viewport: this.viewport, events: this.events }, null, 2));
    console.log(`saved ${this.name}.webm (${this.events.length} events, ${this.t()}s)`);
  }
}

// --- Chat helpers ---------------------------------------------------------------------
const messageBox = (p) => p.getByLabel("Message", { exact: true });

async function waitInputReady(p, timeout = 120000) {
  await p.waitForFunction(() => {
    const ta = document.querySelector('textarea[aria-label="Message"]');
    return ta && !ta.disabled;
  }, null, { timeout });
}

/** Sends a message and logs the waits so the editor can speed them up. */
async function ask(take, text, { label } = {}) {
  const p = take.page;
  await waitInputReady(p);
  await take.type(messageBox(p), text);
  await sleep(350);
  const before = await p.locator("main .prose").count();
  const send = p.getByRole("button", { name: "Send message" });
  await take.click(send);
  const tSend = take.t();
  // First visible activity: a status line or the first words of the reply.
  await p.waitForFunction((n) => {
    const proses = document.querySelectorAll("main .prose");
    const last = proses[proses.length - 1];
    const status = document.querySelector("main [role=status]");
    return proses.length > n && ((last && last.innerText.trim().length > 0) || status);
  }, before + 1, { timeout: 120000 }).catch(() => {});
  const tFirst = take.t();
  await waitInputReady(p, 180000);
  await sleep(600);
  const tDone = take.t();
  take.mark("wait", { label: label || text, start: tSend, firstToken: tFirst, end: tDone });
  return { tSend, tFirst, tDone };
}

async function signIn(take, email, password) {
  const p = take.page;
  await take.goto("/login/");
  await sleep(900);
  await take.type(p.getByLabel("Email"), email, 30);
  await sleep(200);
  await take.type(p.getByLabel("Password", { exact: true }), password, 30);
  await sleep(300);
  await take.click(p.getByRole("button", { name: "Sign in" }));
  await p.waitForURL(/\/(chat|admin)\/?/, { timeout: 30000 });
  await take.restoreCursor();
}

async function newChat(take) {
  const p = take.page;
  await take.click(p.getByRole("button", { name: "New chat" }).first());
  await waitInputReady(p);
  await sleep(700);
}

// --- Takes ------------------------------------------------------------------------------
async function landing(browser) {
  const take = new Take("landing", { width: 1600, height: 900 });
  const p = await take.open(browser);
  await take.goto("/");
  take.chapter("landing", "The landing page", "One design system, dark by default");
  await sleep(3500);
  await take.glide(800, 520, 30);
  await sleep(600);
  take.caption("Smooth scrolling with Lenis");
  await take.wheel(900, 100, 90);
  await sleep(1800);
  await p.locator("#use-cases").scrollIntoViewIfNeeded();
  await sleep(1200);
  take.chapter("use-cases", "Use cases", "Every capability shown in the product's own UI");
  for (const name of [/Search the web/, /Check the weather/, /Report a bug/, /Run the admin desk/, /Ask your documents/]) {
    await take.click(p.getByRole("button", { name }));
    await sleep(1700);
  }
  await take.wheel(1400, 110, 80);
  await sleep(1500);
  await take.wheel(2600, 120, 70);
  await sleep(1500);
  await take.wheel(2000, 120, 70);
  await sleep(2000);
  take.caption("Light theme, designed rather than inverted");
  await p.evaluate(() => window.scrollTo({ top: 0 }));
  await sleep(1200);
  await take.click(p.getByRole("button", { name: /Switch to light theme/ }).first());
  await sleep(2600);
  await take.click(p.getByRole("button", { name: /Switch to dark theme/ }).first());
  await sleep(1800);
  await take.close();
}

async function user(browser) {
  const take = new Take("user", { width: 1600, height: 900 });
  const p = await take.open(browser);

  take.chapter("signin", "Sign in", "Email and password, tokens kept in memory");
  await signIn(take, env.USER_EMAIL, env.USER_PASSWORD);
  await waitInputReady(p).catch(() => {});
  await sleep(1500);

  take.chapter("streaming", "Streaming replies", "Answers appear as they're written");
  await newChat(take);
  await ask(take, "Give me three quick tips for writing a clear email.", { label: "plain answer" });
  await sleep(2500);

  take.chapter("documents", "Ask your documents", "Upload a PDF; the answer cites the pages it used");
  await newChat(take);
  const [chooser] = await Promise.all([
    p.waitForEvent("filechooser"),
    take.click(p.getByRole("button", { name: "Attach a PDF or text file" })),
  ]);
  await chooser.setFiles(PDF);
  const tUp = take.t();
  await p.getByText(/Uploading document|Reading the document/).first().waitFor({ timeout: 30000 }).catch(() => {});
  await take.focus(p.getByRole("status").filter({ hasText: /Uploading|Reading/ }).first(), "indexing status", 2);
  await p.waitForFunction(() => !/Uploading document|Reading the document/.test(document.body.innerText), null, { timeout: 180000 });
  take.mark("wait", { label: "indexing", start: tUp, firstToken: tUp, end: take.t() });
  await sleep(800);
  await take.click(p.getByRole("button", { name: /^Documents/ }));
  await sleep(1200);
  await take.focus(p.locator("[data-slot=sheet-content]").first(), "documents panel", 2.5);
  await sleep(2200);
  await p.keyboard.press("Escape");
  await sleep(800);
  await ask(take, "How many days a week can I work remotely, and which day is in the office?", { label: "document answer" });
  const badge = p.locator('main [aria-label^="Source "]').first();
  if (await badge.count()) {
    take.caption("Hover a citation to see the passage");
    await take.moveTo(badge, { steps: 32 });
    await sleep(1400);
    await take.focus(p.locator("[data-slot=hover-card-content]").first(), "citation preview", 3);
    await sleep(3000);
    await take.glide(take.pos.x + 260, take.pos.y + 120, 24);
  }
  await sleep(1200);
  await take.focus(p.locator("main ol").last(), "numbered sources", 2.5);
  await sleep(2500);

  take.chapter("web", "Web search", "Current questions are answered from the web, with links");
  await newChat(take);
  await ask(take, "What's new in the latest release of Next.js?", { label: "web answer" });
  await take.focus(p.locator("main ol").last(), "web sources", 2.5);
  await sleep(2500);
  const suggestion = p.getByRole("group", { name: "Suggested questions" }).getByRole("button").first();
  if (await suggestion.count()) {
    take.chapter("suggestions", "Suggested questions", "One click asks the next question");
    await take.focus(p.getByRole("group", { name: "Suggested questions" }), "suggestions", 2.5);
    await sleep(1500);
    await take.click(suggestion);
    const tS = take.t();
    await sleep(800);
    await waitInputReady(p, 180000);
    take.mark("wait", { label: "suggestion answer", start: tS, firstToken: tS + 2, end: take.t() });
    await sleep(2000);
  }

  take.chapter("memory", "Memory", "Long chats keep their context; sources survive a reload");
  await ask(take, "Summarise this conversation in two sentences.", { label: "memory answer" });
  await sleep(1500);
  await p.reload({ waitUntil: "load" });
  await take.restoreCursor();
  await waitInputReady(p).catch(() => {});
  await sleep(2500);
  await take.focus(p.locator("main ol").first(), "sources after reload", 2.5);
  await sleep(2000);

  take.chapter("weather", "Live weather", "The agent picks the city and calls a weather tool");
  await newChat(take);
  await ask(take, "What's the weather like in Tokyo right now?", { label: "weather answer" });
  await sleep(2500);

  take.chapter("bug", "Bug reports", "The agent files a ticket for an admin to review");
  await newChat(take);
  await ask(take, "Please report a bug in this app: after I attach a PDF, the upload spinner keeps spinning and the file never appears.", { label: "bug report" });
  await sleep(3000);

  take.chapter("voice", "Voice mode", "Speak your question in Chrome; replies are read aloud");
  await take.focus(p.getByRole("group", { name: "Input mode" }), "voice toggle", 2.5);
  await take.moveTo(p.getByRole("radio", { name: "Voice mode" }).or(p.getByRole("button", { name: "Voice mode" })).first());
  await sleep(2500);
  await take.close();
}

async function admin(browser) {
  const take = new Take("admin", { width: 1600, height: 900 });
  const p = await take.open(browser);
  take.chapter("admin-signin", "Admin sign-in", "Admins land on the dashboard");
  await signIn(take, env.ADMIN_EMAIL, env.ADMIN_PASSWORD);
  await p.getByRole("heading", { name: "Admin dashboard" }).waitFor({ timeout: 30000 });
  await sleep(2500);
  take.chapter("admin-stats", "Admin dashboard", "Users, sessions, requests and server errors");
  await take.focus(p.locator("main, body").locator("div.grid").first(), "stats", 2.5);
  await sleep(2500);

  take.chapter("admin-bugs", "Approve a bug report", "Approval creates the Jira issue and emails the reporter");
  const review = p.getByRole("button", { name: /^Review ticket:/ }).first();
  if (await review.count()) {
    await take.click(review);
    await sleep(2200);
    await take.focus(p.getByRole("dialog").first(), "ticket", 2.5);
    await sleep(1800);
    const approve = p.getByRole("button", { name: "Approve Ticket" }).first();
    if (await approve.isEnabled().catch(() => false)) {
      await take.click(approve);
      await sleep(1500);
      await take.focus(p.getByRole("alertdialog"), "confirm", 2);
      await sleep(1600);
      await take.click(p.getByRole("alertdialog").getByRole("button", { name: "Yes, approve" }));
      const tA = take.t();
      await p.locator("[data-sonner-toast]").first().waitFor({ timeout: 60000 }).catch(() => {});
      take.mark("wait", { label: "jira", start: tA, firstToken: tA, end: take.t() });
      await take.focus(p.locator("[data-sonner-toast]").first(), "approved", 3);
      await sleep(3500);
    }
    await p.keyboard.press("Escape");
    await sleep(1200);
  }

  take.chapter("admin-audit", "Audit log", "Every API request, filterable");
  await take.click(p.getByRole("tab", { name: "Audit log" }));
  await sleep(2200);
  await take.type(p.getByLabel("Filter by path"), "/api/chat", 60);
  await sleep(2500);
  await take.focus(p.locator("table").first(), "audit rows", 2.5);
  await sleep(2000);

  take.chapter("admin-users", "Users and sessions", "Revoke sessions or ban an account");
  await take.click(p.getByRole("tab", { name: /Users/ }));
  await sleep(2000);
  await take.type(p.getByLabel("Search users by email"), env.USER_EMAIL.split("@")[0], 60);
  await sleep(2200);
  const row = p.locator("tr", { hasText: env.USER_EMAIL }).first();
  const sessionsButton = row.getByRole("button").first();
  if (await sessionsButton.count()) {
    await take.click(sessionsButton);
    await sleep(2500);
    await take.focus(p.getByRole("dialog").first(), "sessions", 2.5);
    await sleep(2000);
    await p.keyboard.press("Escape");
    await sleep(800);
  }
  const ban = row.getByRole("button", { name: /Ban/ }).first();
  if (await ban.count()) {
    await take.moveTo(ban);
    await sleep(1800);
  }
  take.caption("The theme switch works everywhere");
  await take.click(p.getByRole("button", { name: /Switch to light theme/ }).first());
  await sleep(2500);
  await take.click(p.getByRole("button", { name: /Switch to dark theme/ }).first());
  await sleep(1500);
  await take.close();
}

async function mobile(browser) {
  const take = new Take("mobile", { width: 390, height: 844 });
  const p = await take.open(browser, { dpr: 2 });
  take.chapter("mobile", "On a phone", "The same app, built for small screens");
  await signIn(take, env.USER_EMAIL, env.USER_PASSWORD);
  await waitInputReady(p).catch(() => {});
  await sleep(2000);
  await take.click(p.getByRole("button", { name: "Open conversations" }));
  await sleep(2500);
  await p.keyboard.press("Escape");
  await sleep(1200);
  await take.click(p.getByRole("button", { name: /^Documents/ }));
  await sleep(2200);
  await p.keyboard.press("Escape");
  await sleep(1000);
  await ask(take, "Give me one tip for a productive morning.", { label: "mobile answer" });
  await sleep(2500);
  await take.close();
}

async function weather(browser) {
  // Replaces the user take's weather chapter: an English city keeps the suggestions in
  // English on the deployed build, which predates the suggestion-language fix.
  const take = new Take("weather", { width: 1600, height: 900 });
  const p = await take.open(browser);
  await signIn(take, env.USER_EMAIL, env.USER_PASSWORD);
  await waitInputReady(p).catch(() => {});
  await sleep(1000);
  take.chapter("weather", "Live weather", "The agent picks the city and calls a weather tool");
  await newChat(take);
  await ask(take, "What's the weather like in London right now?", { label: "weather answer" });
  await sleep(3000);
  await take.close();
}

const takes = { landing, user, admin, mobile, weather };
const browser = await chromium.launch();
try {
  for (const name of process.argv.slice(2)) {
    console.log(`recording ${name}…`);
    await takes[name](browser);
  }
} finally {
  await browser.close();
}
