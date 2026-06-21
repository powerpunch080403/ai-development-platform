# Agent Instructions

이 저장소는 `ai-development-platform` v2 구현 저장소다.

1. 설계나 제품 방향을 변경하기 전에 `ai-development-platform-design`의 accepted ADR을 확인한다.
2. 방향 변경이 필요하면 구현에서 임의 확정하지 않고 design repository의 ADR 또는 Open Questions를 먼저 갱신한다.
3. `ai-game-company-server`의 v1 코드를 복사하거나 기존 구조를 새 제품 결정으로 간주하지 않는다.
4. Discord 인터페이스나 결합 코드를 만들지 않는다.
5. Secret, API key, token, credential, `.env`, local DB, artifact, worktree, runtime log와 사용자 project 내용을 commit하지 않는다.
6. Human, Owner, Worker, Node와 Remote Test Runner Identity를 혼합하지 않는다.
7. 사용자가 Worker나 Test Runner를 직접 조작하는 UX를 만들지 않는다.
8. Public repository hygiene와 `.gitignore` 경계를 유지한다.
9. Python은 명확한 type hint, 작은 module, pathlib와 OS-neutral abstraction을 우선한다.
10. TypeScript는 strict mode, 명시적인 shared contract와 작은 React component를 우선한다.
11. Shell command를 문자열로 조합하기보다 executable과 argument array 경계를 유지한다.
12. 실행 명령이나 개발 흐름을 바꾸면 README와 `scripts/` 문서도 함께 갱신한다.
13. 현재 Slice 범위를 넘는 기능은 placeholder 또는 Open Question으로 남긴다.
14. 사용자 지시 없이 commit하거나 push하지 않는다.
