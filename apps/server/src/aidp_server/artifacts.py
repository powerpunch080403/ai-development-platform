from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from sqlalchemy.orm import Session
from aidp_server.config import Settings, ensure_runtime_dirs
from aidp_server.db.models import ArtifactKind, ArtifactRef


def create_text_artifact(
    session: Session,
    settings: Settings,
    *,
    content: str,
    kind: ArtifactKind,
    user_id: str,
    project_id: str,
    repository_id: str,
    task_id: str,
    attempt_id: str,
    worker_id: str | None,
) -> ArtifactRef:
    _, root = ensure_runtime_dirs(settings)
    relative = Path(attempt_id) / f"{uuid4()}.txt"
    target = (root / relative).resolve()
    if root not in target.parents:
        raise ValueError("Unsafe artifact path")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    target.write_bytes(data)
    ref = ArtifactRef(
        owner_type="task_attempt",
        owner_id=attempt_id,
        local_user_id=user_id,
        project_id=project_id,
        repository_id=repository_id,
        task_id=task_id,
        task_attempt_id=attempt_id,
        worker_id=worker_id,
        kind=kind,
        storage_path=relative.as_posix(),
        content_type="text/plain; charset=utf-8",
        size_bytes=len(data),
        checksum=sha256(data).hexdigest(),
    )
    session.add(ref)
    session.flush()
    return ref


def read_text_artifact(ref: ArtifactRef, settings: Settings) -> str:
    _, root = ensure_runtime_dirs(settings)
    target = (root / ref.storage_path).resolve()
    if root not in target.parents:
        raise ValueError("Unsafe artifact path")
    return target.read_text(encoding="utf-8")
