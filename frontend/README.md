# Chat frontend

The Next.js app, in [`Chatbot/`](Chatbot/). It's built as a static export and served by
the FastAPI backend, so in production it calls the API on the same origin.

## Setup

Requires Node.js 24 and pnpm, and the backend running on port 8000.

```bash
cd frontend/Chatbot
pnpm install
pnpm dev               # http://localhost:3000
```

The backend's `CORS_ORIGINS` must include `http://localhost:3000` for local development.

| Script | What it does |
|---|---|
| `pnpm dev` | Development server |
| `pnpm build` | Static export into `out/` |
| `pnpm lint` | ESLint |
| `pnpm run build:deploy` | Builds for production and copies the result to `backend/app/frontend_build`. `deploy.sh` runs this |
| `pnpm run generate:api-types` | Regenerates `types/api.ts` from the backend's OpenAPI schema. Needs `backend/app/.env` |

### Settings

`NEXT_PUBLIC_API_URL` is the backend's origin. It defaults to `http://localhost:8000`, and
the production build sets it to empty so requests go to the same origin.

## Routes

| Route | Page |
|---|---|
| `/` | Landing page |
| `/login`, `/register` | Sign in and sign up |
| `/chat` | Chat, conversations and documents. Requires sign-in |
| `/admin` | Admin dashboard. Requires admin permissions; admins land here after sign-in |

Pages are protected in the browser by `hooks/useAuth.ts`; the backend checks every
request as well.

## How it works

- **Auth:** the access token is kept in memory only (`lib/auth/tokenStorage.ts`). On
  load and before it expires, `lib/api/client.ts` gets a new one from `/api/auth/refresh`
  using the HTTP-only refresh cookie.
- **Streaming:** `lib/api/chatApi.ts` posts to `/api/chat` and reads the SSE stream with
  `lib/stream/sseParser.ts`; `hooks/useChat.ts` builds the message as tokens arrive.
- **Admin data** is fetched with SWR in `components/admin/`.
- **Theme:** `next-themes`, dark by default, with a toggle on every page.

## Structure

```
Chatbot/
  app/
    (marketing)/     Landing page
    (auth)/          Sign in and sign up, sharing one layout
    (app)/           Chat and admin
  components/
    marketing/       Landing page sections
    auth/            Sign-in form
    chat/            Chat shell, messages, input, documents
    admin/           Dashboard tabs and cards
    ui/              shadcn/ui components
  hooks/             Auth, chat, conversations, documents, voice
  lib/               API clients, token storage, SSE parser, voice
  types/api.ts       Generated from the backend; don't edit by hand
```

The visual design system is recorded in `Chatbot/DESIGN.md` when present locally.
