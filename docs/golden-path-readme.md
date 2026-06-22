# README Edit Golden Path

이 문서는 Local Worker Golden Path 1의 현재 검증 범위를 설명한다. 실제 AI Worker가 아니라 앱이 만든 격리 Worktree를 사용자가 직접 수정하는 Manual 흐름이다.

## 사전 조건

- Git, Python 3.11+, uv, Node.js와 pnpm
- migration이 적용된 Local Runtime server
- `http://localhost:5173`에서 실행 중인 Web UI
- CLI로 발급한 Web UI pairing code
- 최소 initial commit과 local `user.name`/`user.email`이 있는 clean Git repository

```powershell
uv run --project apps/server alembic upgrade head
uv run --project apps/server uvicorn aidp_server.main:app --reload --host 127.0.0.1 --port 8000
uv run --project apps/server python -m aidp_server.cli auth pairing-code
pnpm -C apps/web dev
```

## Web UI 수동 절차

1. Pairing code로 로그인한다.
2. Project를 만들고 clean Git repository를 primary repository로 등록한다.
3. Work Item과 repository가 연결된 draft Task를 만든다.
4. Attempt와 Manual Worker record를 만들고 Worker가 Attempt를 claim하게 한다.
5. Create Worktree를 누른다. Worktree는 app data의 `worktrees/<project>/<repository>/<attempt>` 아래에 생성된다.
6. 표시된 Worktree 경로의 `README.md`에 한 줄을 직접 추가한다.
7. Refresh status와 View diff로 변경을 확인하고 Commit result를 누른다.
8. Review-ready 목록에서 Attempt를 선택하고 diff와 artifact를 확인한다.
9. Approve를 누른 뒤 Prepare merge로 source clean/base HEAD 조건을 확인한다.
10. Squash merge를 누른다. Local default/base branch에 단일 squash commit이 생성된다.
11. Cleanup Worktree를 눌러 app-managed Worktree를 제거한다.

Remote fetch/push는 수행하지 않는다. Source repository가 dirty하거나 HEAD가 Worktree 생성 당시 base에서 바뀌었으면 merge는 `409`로 차단된다.

## 자동 E2E 검증

```powershell
cd apps/server
uv run pytest tests/test_golden_path_readme_e2e.py
```

테스트는 시스템 임시 디렉터리에 Git repository를 만들고 pairing부터 squash merge까지 실제 API와 Git 명령으로 검증한다. 구현 repository의 HEAD는 테스트 전후 동일해야 한다.

## 기대 상태 전이

```text
Task: draft → running → waiting_for_review → completed
TaskAttempt: created → running_worker → committed → merged
GitWorktree: ready → dirty_result → committed → cleanup_pending → cleaned
Worker: available → claimed → available
```

Artifact 파일은 app data `artifacts/<attempt-id>/` 아래에 있고 SQLite에는 상대 경로, 크기와 SHA-256 checksum만 저장한다. E2E는 diff patch, pre-commit Git status, result commit log와 merge report를 확인한다.

## 현재 범위 밖

- 실제 Worker process와 Mock/Manual Adapter 정식 구현
- Codex/Antigravity CLI Adapter
- Remote Test Runner
- Force cleanup과 cleanup background scheduler
- 전체 Approval Policy Engine과 Owner Grant
- Team Mode, 중앙 Approval Group과 merge queue
- Desktop App Shell
