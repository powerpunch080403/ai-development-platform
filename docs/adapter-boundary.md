# Adapter Boundary

## 현재 Adapter

- Mock Worker Adapter: Golden Path E2E 테스트 및 파이프라인 검증용
- Manual Worker Adapter: Web UI를 통한 수동 편집 흐름 (기본 파이프라인 수동 검증용)

## 후속 Adapter

- Codex CLI Owner Adapter
- Antigravity CLI Worker Adapter
- External CLI Worker Adapter
- **External CLI Dry Run Adapter**: CLI Adapter의 Context Package 전달 및 Process Runner 연동 계약(Contract)을 실제 AI 모델 호출 없이 안전하게 검증하는 용도

## 중요한 경계

- Adapter는 main/default 단일 branch에 직접 merge하지 않는다.
- Adapter는 Task Attempt 범위 밖에서 실행하지 않는다.
- Adapter는 worktree 밖 파일을 수정하지 않는다.
- Adapter 결과는 result branch commit으로 남긴다.
- Owner review와 approval/squash merge는 별도 단계다.

## Process Runner Baseline

현재 저장소에는 외부 CLI 프로세스 실행을 안전하게 감싸는 `Process Runner`의 기반이 구현되어 있다.
- `shell=True` 없이 인자 배열 기반으로만 실행한다.
- 허용된 Working Directory (저장소 혹은 워크트리 경로) 내에서만 실행을 허가한다.
- timeout 및 stdout/stderr 아티팩트 저장을 지원한다.
- API 키 등 민감정보 마스킹(Redaction)을 수행한다.
- **아직 실제 Codex/Antigravity CLI를 실행하지 않으며, 임의 명령어 실행 UI도 존재하지 않는다.**

## External CLI Adapter Contract Baseline

현재 저장소에는 외부 CLI와 통신하기 위한 계약의 기반이 구현되어 있다.
- 실제 AI CLI를 실행하지 않고, 계약과 데이터 흐름을 검증하기 위한 `external_cli_dry_run` Adapter가 구현되어 있다.
- Dry-run은 서버에서 지정한 안전한 고정 명령어만 실행하며, 레포지토리 파일이나 브랜치를 변경하지 않는다.
- `TaskAttempt` 및 Worker/Process Run 간의 연결, Context Package 아티팩트의 생성 및 저장이 검증되었다.
- 실제 동작(파일 변경, 결과 Commit 생성 등)은 Dry-run 범위를 벗어나며, 후속 단계에서 다루게 된다.

## Write scope boundary

Task는 repository root 기준 상대 경로 allowlist인 `write_scope`를 가진다. 기본값 `.`은 전체 worktree를 허용한다. Mock, Manual과 향후 External CLI Adapter의 결과는 commit 전에 staged, unstaged, untracked 경로를 모두 검사하며 scope 밖 변경이나 허용되지 않은 새 파일이 있으면 결과 commit을 만들지 않는다. 이 검증은 실제 AI CLI Adapter 연결 전 필수 안전장치다.
