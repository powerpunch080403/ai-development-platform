# Remote Test Runner Agent Placeholder

이 디렉터리는 ADR-0012의 Remote Test Runner Agent를 위한 placeholder다. 실제 Agent code는 Local Worker Golden Path와 목표 CLI Adapter 통합 이후의 MVP Slice에서 작성한다.

- Remote Test Runner는 Owner Tool이나 독립 AI Worker가 아닌 Worker Capability다.
- Owner가 직접 조종하지 않고 Worker가 Task Attempt 범위에서 호출한다.
- test, build와 lint만 수행한다.
- 코드 수정, commit, merge와 배포를 하지 않는다.
- 산출물은 Main App Artifact Store에 업로드하고 `artifact_ref`로 연결할 예정이다.

현재는 실행 code, network protocol과 credential을 포함하지 않는다.
