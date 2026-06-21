$ErrorActionPreference = "Stop"

function Show-ToolVersion([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        Write-Warning "$Name is not available on PATH."
        return
    }

    & $Name --version
}

Write-Host "AI Development Platform bootstrap validation"
Write-Host "This is command guidance, not an integrated dev runner."
Write-Host ""
Write-Host "Tool versions:"
Show-ToolVersion "uv"
Show-ToolVersion "pnpm"
Write-Host ""
Write-Host "Server (PowerShell 1):"
Write-Host "  uv sync --project apps/server"
Write-Host "  uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "Web (PowerShell 2):"
Write-Host "  pnpm install"
Write-Host "  pnpm -C apps/web dev"
Write-Host ""
Write-Host "Checks:"
Write-Host "  uv run --project apps/server pytest"
Write-Host "  pnpm -r build"
