# Web

Desktop App Shell에서 재사용할 수 있는 React/TypeScript/Vite Web UI skeleton이다.

현재는 pairing/session과 Project/Repository UI 위에 일반 또는 Project Conversation 생성, user Message append, Agent Run record 생성·목록과 Tool Registry 표시를 포함한다. 실제 AI 응답과 Tool 실행은 없다. Session token은 HttpOnly cookie만 사용한다.

## Windows PowerShell

```powershell
pnpm install
pnpm -C apps/web build
pnpm -C apps/web dev
```

저장소 루트에서 실행하는 것을 기준으로 한다. Dev server 기본 주소는 `http://localhost:5173`이다. Server의 `AIDP_WEB_ORIGIN`도 이 주소와 일치해야 한다.

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

API 기본 주소는 `http://localhost:8000`이다. 변경할 때는 `apps/web/.env.example`을 복사한 local `.env`에서 `VITE_AIDP_API_BASE_URL`을 설정한다. 실제 `.env`는 commit하지 않는다.

pnpm 11의 dependency build 보안 정책에 따라 Vite가 요구하는 `esbuild`만 `pnpm-workspace.yaml`의 `allowBuilds`에서 허용한다. 다른 dependency build script는 검토 없이 추가하지 않는다.

File picker는 아직 없으므로 repository의 local path를 직접 입력한다. 첫 repository에서 role을 Automatic으로 두면 `primary`, 이후에는 `unknown`으로 등록된다. Dirty 표시는 변경을 자동 수정·stash·commit하지 않으며 Refresh status는 read-only 조회만 수행한다.
