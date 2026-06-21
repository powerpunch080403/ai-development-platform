#!/usr/bin/env sh
set -eu

echo "AI Development Platform bootstrap validation"
echo "This is command guidance, not an integrated dev runner."
echo
echo "Tool versions:"
if command -v uv >/dev/null 2>&1; then uv --version; else echo "uv: not available on PATH"; fi
if command -v pnpm >/dev/null 2>&1; then pnpm --version; else echo "pnpm: not available on PATH"; fi
echo
echo "Server (terminal 1):"
echo "  uv sync --project apps/server"
echo "  uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000"
echo
echo "Web (terminal 2):"
echo "  pnpm install"
echo "  pnpm -C apps/web dev"
echo
echo "Checks:"
echo "  uv run --project apps/server pytest"
echo "  pnpm -r build"
