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

등록한 repository absolute path와 Git status metadata도 local runtime data다. 사용자 repository를 이 source repository 아래로 복사하지 않고, DB나 status 출력물을 fixture 또는 문서에 commit하지 않는다. Automated test의 Git commit은 시스템 임시 디렉터리의 test repository에서만 만든다.

Pairing code와 session token 원문은 secret runtime data다. Pairing code는 CLI에 한 번만 표시하고 두 값 모두 DB에는 hash만 저장한다. API response, application log, test fixture와 문서 예시에 실제 값을 남기지 않는다. Web UI는 session token을 localStorage 또는 JavaScript 상태로 복사하지 않는다.

기본 `runtime-data/`와 그 아래 SQLite 파일은 local-only 상태다. Migration 검증이나 server 실행으로 DB가 생성되어도 Git status에 나타나면 안 된다. Migration source와 `uv.lock`만 commit한다.

Dependency resolution을 재현하기 위한 `apps/server/uv.lock`과 루트 `pnpm-lock.yaml`은 commit 대상이다. `.venv`, `node_modules`와 generated `dist`는 commit하지 않는다.

Repository status 기능은 Git read-only 명령만 실행한다. 실제 사용자 repository에서 fetch, branch, commit, worktree, stash, reset 또는 merge를 자동 실행하지 않는다.

Message, Tool arguments, error와 Audit metadata에는 token, credential, 환경 변수 원문이나 사용자 source 내용을 불필요하게 복제하지 않는다. Tool Registry seed는 공개 가능한 이름과 정책 metadata만 포함하며 실제 실행 결과와 transcript는 runtime DB에만 둔다.

Worker capability, claim, lease, Task instructions와 result summary는 local runtime DB 데이터다. 실제 Worker process log, 사용자 파일, worktree와 artifact를 source repository에 만들거나 commit하지 않는다.

Worktree와 artifact는 반드시 app data의 ignored `worktrees/`, `artifacts/` 아래에 둔다. SQLite에는 artifact 상대 경로, 크기와 checksum만 저장한다. 테스트 commit은 시스템 임시 Git repository의 작업 branch에서만 만든다.

Squash merge 테스트도 시스템 임시 repository에서만 수행한다. 구현 source repository에는 테스트 branch/commit을 만들지 않으며 merge API는 remote fetch/push를 호출하지 않는다.

Golden Path E2E는 구현 repository HEAD를 시작과 종료 시 비교한다. 테스트 DB, 임시 repository, worktree와 artifact는 pytest 임시 디렉터리에만 생성하며 source Git status에 포함하지 않는다.

Cleanup은 configured app-data Worktree root 아래의 Git-registered path만 제거한다. Source repository, app-data root, artifacts와 SQLite records에는 recursive delete를 수행하지 않는다.
