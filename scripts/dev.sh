#!/usr/bin/env sh
set -eu

echo "AI Development Platform monorepo skeleton"
echo "No integrated development launcher is implemented yet."
echo
echo "Server hint:"
echo "  uv sync --project apps/server"
echo "  uv run --project apps/server fastapi dev apps/server/src/aidp_server/main.py"
echo
echo "Web hint:"
echo "  pnpm install"
echo "  pnpm web:dev"
