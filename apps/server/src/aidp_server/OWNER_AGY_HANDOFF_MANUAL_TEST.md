# Owner AGY Handoff Manual Test

This document outlines how to manually verify the actual `agy` handoff execution locally. Because the automated tests mock out the real AGY CLI execution to maintain safe CI boundaries, manual verification is required when changing the actual process boundary.

## Prerequisites

1. Have the `antigravity_cli` compiled or mocked in your environment.
2. Set up the local `.env` with:
   ```env
   ALLOW_OWNER_AGY_WORKER_RUN=true
   ANTIGRAVITY_CLI_PATH=/path/to/your/cli
   ```

## Steps to Verify

1. **Start the API Server**
   ```powershell
   cd apps/server
   uv run uvicorn aidp_server.main:app --reload
   ```

2. **Authenticate and Create a Project**
   Use the UI or curl to create a user and project.

3. **Create a Task via Tool**
   Issue a `task.create` tool call via the Owner interface.

4. **Start a Task Attempt**
   Issue a `worker.start_task_attempt` tool call with `"worker_adapter": "agy"`.
   Verify that a `WorkerRun` and `TaskAttempt` are created.

5. **Run the Task Attempt**
   Issue a `worker.run_task_attempt` tool call with the created `worker_run_id`.

   *Expected Immediate Result:*
   - Tool call returns `SUCCEEDED` synchronously.
   - Result JSON includes `"status": "handoff_started"` and `"fresh_worker_context": true`.

6. **Verify Background Execution**
   - Wait for the background process to complete (time depends on `timeout_seconds`).
   - Check the `process_runs` table in the database to see the executed command.
   - Check the `worker_runs` table to verify it transitioned from `RUNNING` to `SUCCEEDED` or `FAILED`.
   - Verify the generated CLI transcript artifact and the report artifact.
