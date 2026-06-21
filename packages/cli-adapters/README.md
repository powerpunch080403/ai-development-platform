# CLI Adapters Placeholder

외부 Agent Process Adapter contract를 위한 package다.

- Owner Adapter 목표: Codex CLI
- Worker Adapter 목표: Antigravity CLI
- Mock Adapter와 Manual Adapter: 개발, pipeline 검증과 복구용 fallback
- Adapter는 Owner/Worker Identity가 아니라 교체 가능한 외부 process 구현체

실제 CLI 실행, authentication, interactive prompt 처리와 output parsing은 후속 Slice에서 구현한다.
