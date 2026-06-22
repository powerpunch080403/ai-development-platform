# README Edit Golden Path

README 변경 Task는 `write_scope.paths = ["README.md"]`처럼 허용 범위를 좁힐 수 있다. 결과 commit 전에 Git changed path를 검증하므로 다른 파일 변경은 commit 및 review-ready 전이를 차단한다. `write_scope`를 생략하면 기존 호환 기본값 `.`을 사용한다.

이 문서는 Local Worker Golden Path의 현재 검증 범위를 설명한다. 현재 MVP는 실제 AI Worker를 실행하지 않으며, 다음 3가지 방법으로 파이프라인을 검증한다.

## A. Manual Worker Golden Path

Web UI 기반 수동 작업 흐름이다.

```text
pairing
→ project/repository
→ work item/task/attempt
→ manual worker register
→ claim
→ start manual worker
→ user edits files in worktree
→ submit manual result
→ review
→ approve
→ prepare merge
→ squash merge
→ cleanup
```

## B. Mock Worker Golden Path

결정론적 E2E 테스트를 위한 자동화 흐름이다.

```text
pairing
→ project/repository
→ task instructions with MOCK_APPEND
→ attempt
→ mock worker register
→ claim
→ run mock worker
→ review
→ approve
→ prepare merge
→ squash merge
→ cleanup
```

## C. Raw Worktree Debug Flow

디버깅, 복구, 및 향후 Adapter 재사용을 위한 저수준 API 흐름이다.

```text
create worktree raw
→ edit manually
→ commit result raw
```

## 자동 E2E 검증

```powershell
cd apps/server
uv run pytest tests/test_golden_path_readme_e2e.py
uv run pytest tests/test_mock_worker_adapter.py
uv run pytest tests/test_manual_worker_adapter.py
```

테스트는 시스템 임시 디렉터리에 Git repository를 만들고 pairing부터 squash merge까지 실제 API와 Git 명령으로 검증한다. 구현 repository의 HEAD는 테스트 전후 동일해야 한다.
