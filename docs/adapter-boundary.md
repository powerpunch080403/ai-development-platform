# Adapter Boundary

## 현재 Adapter

- Mock Worker Adapter: Golden Path E2E 테스트 및 파이프라인 검증용
- Manual Worker Adapter: Web UI를 통한 수동 편집 흐름 (기본 파이프라인 수동 검증용)

## 후속 Adapter

- Codex CLI Owner Adapter
- Antigravity CLI Worker Adapter
- External CLI Worker Adapter

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
