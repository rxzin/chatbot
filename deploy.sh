#!/usr/bin/env bash
#
# Builds the frontend, updates the production database, and deploys to FastAPI Cloud.
# Safe to run repeatedly: migrations and the seed only apply what's missing.
#
#   ./deploy.sh                Do everything, after asking for confirmation
#   ./deploy.sh --yes          Skip the confirmation, for CI
#   ./deploy.sh --no-frontend  Reuse the last frontend build
#   ./deploy.sh --no-db        Skip migrations and the seed
#   ./deploy.sh --no-deploy    Do everything except the upload
#
# Settings come from backend/app/.env.production, or the ENV_FILE environment variable.
# The app itself reads the variables set in the FastAPI Cloud dashboard, so update those
# separately when they change.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend/app"
FRONTEND="$ROOT/frontend/Chatbot"
ENV_FILE="${ENV_FILE:-$BACKEND/.env.production}"

# The FastAPI Cloud CLI prints emoji, which crashes Python on Windows without this.
export PYTHONUTF8=1

BUILD_FRONTEND=true
UPDATE_DB=true
DEPLOY=true
ASSUME_YES=false

for arg in "$@"; do
  case "$arg" in
    --no-frontend) BUILD_FRONTEND=false ;;
    --no-db) UPDATE_DB=false ;;
    --no-deploy) DEPLOY=false ;;
    --yes) ASSUME_YES=true ;;
    *)
      echo "Unknown option: $arg" >&2
      sed -n '2,13p' "${BASH_SOURCE[0]}" >&2
      exit 2
      ;;
  esac
done

step() { printf '\n==> %s\n' "$1"; }
fail() { printf 'Error: %s\n' "$1" >&2; exit 1; }

# Runs a command with production settings. These take priority over backend/app/.env.
with_production_env() {
  (cd "$BACKEND" && uv run --frozen --env-file "$ENV_FILE" "$@")
}

step "Checking prerequisites"
command -v uv >/dev/null || fail "uv isn't installed."
if [ "$BUILD_FRONTEND" = true ]; then
  command -v pnpm >/dev/null || fail "pnpm isn't installed."
fi

if [ "$UPDATE_DB" = true ]; then
  [ -f "$ENV_FILE" ] || fail "$ENV_FILE doesn't exist."
  if grep -qE '^[A-Z_]+=<' "$ENV_FILE"; then
    grep -oE '^[A-Z_]+=<' "$ENV_FILE" | sed 's/=<$//; s/^/  /' >&2
    fail "Replace the placeholders above in $ENV_FILE first."
  fi

  # Read from the app's own settings, so this shows the database that will really be used.
  # Only the host and database name are printed, never the password.
  DB_TARGET="$(with_production_env python -c \
    "from core.config import getSettings as g; s = g(); print(f'{s.POSTGRESQL_SERVER}/{s.POSTGRESQL_DATABASE}')" \
    | tail -n 1 | tr -d '\r')"
  echo "Database: $DB_TARGET"
fi

if [ "$ASSUME_YES" = false ]; then
  [ -t 0 ] || fail "No terminal to confirm in. Pass --yes to run without asking."
  read -r -p "Continue? [y/N] " answer
  case "$answer" in
    y | Y) ;;
    *) echo "Cancelled."; exit 0 ;;
  esac
fi

# The frontend goes first because it has no side effects. A build error stops the script
# before the database changes.
if [ "$BUILD_FRONTEND" = true ]; then
  step "Building the frontend"
  (cd "$FRONTEND" && pnpm install --frozen-lockfile && pnpm run build:deploy)
fi

if [ "$DEPLOY" = true ] && [ ! -f "$BACKEND/frontend_build/index.html" ]; then
  fail "No frontend build to upload. Run without --no-frontend."
fi

# Migrations run before the upload, so new code never runs against an old schema.
if [ "$UPDATE_DB" = true ]; then
  step "Applying migrations"
  with_production_env alembic upgrade head

  step "Seeding roles, permissions, and the admin account"
  with_production_env python seed.py
fi

if [ "$DEPLOY" = true ]; then
  step "Deploying to FastAPI Cloud"
  (cd "$BACKEND" && uv run --frozen fastapi deploy)
fi

step "Done"
