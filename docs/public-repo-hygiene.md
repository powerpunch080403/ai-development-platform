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
