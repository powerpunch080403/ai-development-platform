# Web

Desktop App Shell에서 재사용할 수 있는 React/TypeScript/Vite Web UI skeleton이다.

Attempt에서 Worktree 생성, path/branch/base 표시, status/diff 조회, manual result commit과 artifact text 조회를 제공한다. 파일 편집기는 없으며 사용자가 표시된 worktree path에서 직접 수정한다. 기본 branch merge는 하지 않는다.
Review-ready 목록, diff와 merge 조건, approve/reject/prepare/squash 버튼을 제공한다. Squash는 명시적 approve 이후 local base branch에만 수행한다.

현재 UI는 AI Worker를 실행하지 않는다. Create Worktree 후 표시된 경로를 사용자가 직접 편집하고 Commit result로 제출한다. 전체 수동 절차는 `docs/golden-path-readme.md`에 있다.

Squash merge 후 Cleanup Worktree 패널에서 app-managed Worktree만 안전하게 제거할 수 있다. Cleanup은 artifacts나 source repository를 삭제하지 않는다.

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
