# Adapter Boundary

## 현재 Adapter

- Mock Worker Adapter: Golden Path E2E 테스트 및 파이프라인 검증용
- Manual Worker Adapter: Web UI를 통한 수동 편집 흐름 (기본 파이프라인 수동 검증용)

## 후속 Adapter

- Codex CLI Owner Adapter
- Antigravity CLI Worker Adapter
- External CLI Worker Adapter

## 중요한 경계

- Adapter는 main/default branch에 직접 merge하지 않는다.
- Adapter는 Task Attempt 범위 밖에서 실행하지 않는다.
- Adapter는 worktree 밖 파일을 수정하지 않는다.
- Adapter 결과는 result branch commit으로 남긴다.
- Owner review와 approval/squash merge는 별도 단계다.

## Process Runner로 넘겨야 할 후보

*(아직 구현하지 않은 외부 Process Runner를 위한 요구사항)*
- command timeout
- stdout/stderr capture
- cancellation
- environment isolation
- working directory validation
- artifact capture
- process exit code handling
- secret redaction
