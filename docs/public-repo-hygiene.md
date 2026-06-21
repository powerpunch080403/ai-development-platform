# Public Repository Hygiene

이 repository는 Public이다. Source code와 안전한 예시만 version control한다.

## Commit 금지

- Secret, API key와 access token
- `.env`와 환경별 credential
- Local SQLite database
- 사용자 Project source와 private repository checkout
- Runtime data와 Session 정보
- Generated artifact와 test output
- Git worktree
- Runtime log와 crash dump
- CLI 또는 Node credential

`.env.example`에는 비밀이 아닌 placeholder만 기록하고 실제 값은 넣지 않는다. 작업 전 `git status --short`와 staged diff를 확인한다.

Runtime data는 source repository가 아니라 App-managed Local Runtime의 app data directory에 저장한다.

Pairing code와 session token 원문은 secret runtime data다. Pairing code는 CLI에 한 번만 표시하고 두 값 모두 DB에는 hash만 저장한다. API response, application log, test fixture와 문서 예시에 실제 값을 남기지 않는다. Web UI는 session token을 localStorage 또는 JavaScript 상태로 복사하지 않는다.

기본 `runtime-data/`와 그 아래 SQLite 파일은 local-only 상태다. Migration 검증이나 server 실행으로 DB가 생성되어도 Git status에 나타나면 안 된다. Migration source와 `uv.lock`만 commit한다.

Dependency resolution을 재현하기 위한 `apps/server/uv.lock`과 루트 `pnpm-lock.yaml`은 commit 대상이다. `.venv`, `node_modules`와 generated `dist`는 commit하지 않는다.
