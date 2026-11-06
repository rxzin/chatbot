# Chat demo video

A walkthrough of every feature, made with [Remotion](https://www.remotion.dev): real
footage of the live site, recorded with Playwright, with chapter titles, zooms, sped-up
waits and animated "how it works" scenes. Two cuts from the same footage:

- **Highlights** (`out/chat-highlights.mp4`): a fast reel just under a minute. Typing and
  scrolling run at about 3×, model waits at 10×, and key moments (citations, sources,
  the Jira approval) slow back down so they can be read.
- **Demo** (`out/chat-demo.mp4`): the full walkthrough, about 4:30, with the
  architecture, agent, memory and safeguards scenes.

Sign-in is shown once, at the start.

Footage, renders, credentials and the demo PDF are gitignored: the footage shows real
email addresses.

## Re-render (no recording needed)

```bash
cd demo-video
pnpm install
pnpm run render:highlights          # out/chat-highlights.mp4
pnpm run render                     # out/chat-demo.mp4
node scripts/split-chapters.cjs     # per-chapter clips of the full cut
node scripts/print-timeline.cjs     # chapter plan of the highlights (add "full" for the other)
pnpm run studio                     # preview and tweak in the browser
```

Rendering needs the footage in `public/footage/`. Pacing, captions and zooms come from
the timelines in `src/data/*.json`, built by `src/timeline.ts`: each cut is a profile
(`FULL`, `HIGHLIGHTS`) with its chapter list, per-chapter speed, skip and length, and the
speeds for model waits and key moments.

## Re-record the footage

1. Create `demo-video/demo.env` (gitignored):

   ```
   SITE=https://razin.tech
   ADMIN_EMAIL=...
   ADMIN_PASSWORD=...
   USER_EMAIL=...
   USER_PASSWORD=...
   ```

2. Make the fictional handbook: `node scripts/make_pdf.mjs "$PWD/northwind-handbook.pdf"`
3. Record: `pnpm run record` (takes: `landing user weather admin mobile`; you can pass
   any subset to `node scripts/recorder.mjs`). Each take writes `public/footage/<take>.webm`
   and `<take>.json`.
4. Copy each `public/footage/<take>.json` to `src/data/`, adding its length in seconds as
   `"duration"`, then render again.

Recording acts on the live site: it uploads the handbook (delete it afterwards, which
also removes its vectors), files a bug report, and approves it, which creates a Jira
issue and emails the user. The bug report has a cooldown per user, so leave a few
minutes between full recordings.

## Notes

- The user take's weather chapter is replaced by the separate `weather` take (see `PLAN`
  in `src/timeline.ts`).
- The voice-mode question is audio only, so the recorder suppresses it; the Voice toggle
  is shown and explained instead.
- Remotion is free for individuals and small teams; see its license for company use.
