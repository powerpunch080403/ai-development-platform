# Web

Desktop App Shell에서 재사용할 수 있는 React/TypeScript/Vite Web UI skeleton이다.

현재는 Local Runtime 연결 상태 placeholder와 `/health` API client만 포함한다. Pairing, Session, Owner chat와 Task UI는 아직 구현하지 않았다.

## Windows PowerShell

```powershell
pnpm install
pnpm -C apps/web build
pnpm -C apps/web dev
```

저장소 루트에서 실행하는 것을 기준으로 한다. Dev server 기본 주소는 `http://127.0.0.1:5173`이다.

Workspace package를 포함한 전체 build:

```powershell
pnpm -r build
```

## Linux/macOS

```bash
pnpm install
pnpm -C apps/web build
pnpm -C apps/web dev
```

pnpm 11의 dependency build 보안 정책에 따라 Vite가 요구하는 `esbuild`만 `pnpm-workspace.yaml`의 `allowBuilds`에서 허용한다. 다른 dependency build script는 검토 없이 추가하지 않는다.
