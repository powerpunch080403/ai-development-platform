from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import subprocess
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aidp_server.auth import CurrentAuth
from aidp_server.db.models import Project, ProjectRepository, ProjectStatus, RepositoryRole, VcsType
from aidp_server.db.session import get_session
from aidp_server.git_utils import GitRepositoryStatus, inspect_git_repository


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank")
        return value


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank")
        return value


class RegisterRepositoryRequest(BaseModel):
    repository_path: str = Field(min_length=1, max_length=4096)
    repository_role: RepositoryRole | None = None


class ProjectView(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class ProjectOpenResult(BaseModel):
    status: str
    path: str


class ProjectRepositoryView(BaseModel):
    id: str
    project_id: str
    repository_path: str
    repository_name: str
    repository_role: str
    vcs_type: str
    default_branch: str | None
    current_branch: str | None
    last_commit_sha: str | None
    is_dirty: bool
    last_status_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class RepositoryStatusView(BaseModel):
    repository_id: str
    is_git_repository: bool
    repository_root: str | None
    current_branch: str | None
    default_branch: str | None
    last_commit_sha: str | None
    is_dirty: bool | None
    porcelain: str | None
    checked_at: datetime | None
    error_code: str | None
    error_message: str | None


router = APIRouter(tags=["projects and repositories"])


def _project_view(project: Project) -> ProjectView:
    return ProjectView(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status.value,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
    )


def _repository_view(repository: ProjectRepository) -> ProjectRepositoryView:
    return ProjectRepositoryView(
        id=repository.id,
        project_id=repository.project_id,
        repository_path=repository.repository_path,
        repository_name=repository.repository_name,
        repository_role=repository.repository_role.value,
        vcs_type=repository.vcs_type.value,
        default_branch=repository.default_branch,
        current_branch=repository.current_branch,
        last_commit_sha=repository.last_commit_sha,
        is_dirty=repository.is_dirty,
        last_status_checked_at=repository.last_status_checked_at,
        created_at=repository.created_at,
        updated_at=repository.updated_at,
        archived_at=repository.archived_at,
    )


def _get_owned_project(session: Session, project_id: str, local_user_id: str) -> Project:
    project = session.scalar(
        select(Project).where(Project.id == project_id, Project.local_user_id == local_user_id)
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _get_owned_repository(
    session: Session, repository_id: str, local_user_id: str
) -> ProjectRepository:
    repository = session.scalar(
        select(ProjectRepository).where(
            ProjectRepository.id == repository_id,
            ProjectRepository.local_user_id == local_user_id,
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repository


def _status_view(
    repository: ProjectRepository,
    inspected: GitRepositoryStatus | None = None,
) -> RepositoryStatusView:
    return RepositoryStatusView(
        repository_id=repository.id,
        is_git_repository=inspected.is_git_repository if inspected else True,
        repository_root=inspected.repository_root if inspected else repository.repository_path,
        current_branch=inspected.current_branch if inspected else repository.current_branch,
        default_branch=inspected.default_branch if inspected else repository.default_branch,
        last_commit_sha=inspected.last_commit_sha if inspected else repository.last_commit_sha,
        is_dirty=inspected.is_dirty if inspected else repository.is_dirty,
        porcelain=inspected.porcelain if inspected else None,
        checked_at=repository.last_status_checked_at,
        error_code=inspected.error_code if inspected else None,
        error_message=inspected.error_message if inspected else None,
    )


def _project_open_path(session: Session, project: Project) -> str:
    repository = session.scalar(
        select(ProjectRepository)
        .where(
            ProjectRepository.project_id == project.id,
            ProjectRepository.archived_at.is_(None),
        )
        .order_by(ProjectRepository.repository_role == RepositoryRole.PRIMARY, ProjectRepository.created_at)
    )
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project has no registered repository to open",
        )
    return repository.repository_path


def _open_file_manager(path: str) -> None:
    resolved = str(Path(path).resolve())
    system = platform.system().lower()
    try:
        if system == "windows":
            os.startfile(resolved)  # type: ignore[attr-defined]
        elif system == "darwin":
            subprocess.Popen(["open", resolved])
        else:
            subprocess.Popen(["xdg-open", resolved])
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not open file manager: {error}",
        ) from error


@router.post("/projects", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(
    request: CreateProjectRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectView:
    project = Project(
        local_user_id=current.user.id,
        name=request.name,
        description=request.description.strip() if request.description else None,
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)
    session.commit()
    return _project_view(project)


@router.get("/projects", response_model=list[ProjectView])
def list_projects(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ProjectView]:
    projects = session.scalars(
        select(Project)
        .where(Project.local_user_id == current.user.id, Project.archived_at.is_(None))
        .order_by(Project.created_at.desc())
    )
    return [_project_view(project) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectView)
def get_project(
    project_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectView:
    return _project_view(_get_owned_project(session, project_id, current.user.id))


@router.patch("/projects/{project_id}", response_model=ProjectView)
def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectView:
    project = _get_owned_project(session, project_id, current.user.id)
    if request.name is not None:
        project.name = request.name.strip()
    if request.description is not None:
        project.description = request.description.strip() if request.description else None
    project.updated_at = datetime.now(timezone.utc)
    session.commit()
    return _project_view(project)


@router.delete("/projects/{project_id}", response_model=ProjectView)
def archive_project(
    project_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectView:
    project = _get_owned_project(session, project_id, current.user.id)
    now = datetime.now(timezone.utc)
    project.status = ProjectStatus.ARCHIVED
    project.archived_at = now
    project.updated_at = now
    session.commit()
    return _project_view(project)


@router.post("/projects/{project_id}/open-in-file-manager", response_model=ProjectOpenResult)
def open_project_in_file_manager(
    project_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectOpenResult:
    project = _get_owned_project(session, project_id, current.user.id)
    path = _project_open_path(session, project)
    _open_file_manager(path)
    return ProjectOpenResult(status="opened", path=path)


@router.post(
    "/projects/{project_id}/repositories",
    response_model=ProjectRepositoryView,
    status_code=status.HTTP_201_CREATED,
)
def register_repository(
    project_id: str,
    request: RegisterRepositoryRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectRepositoryView:
    _get_owned_project(session, project_id, current.user.id)
    inspected = inspect_git_repository(request.repository_path)
    if not inspected.is_git_repository or inspected.error_code or not inspected.repository_root:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": inspected.error_code, "message": inspected.error_message},
        )

    existing = list(
        session.scalars(
            select(ProjectRepository).where(
                ProjectRepository.project_id == project_id,
                ProjectRepository.archived_at.is_(None),
            )
        )
    )
    normalized_root = str(Path(inspected.repository_root).resolve())
    normalized_key = os.path.normcase(normalized_root)
    if any(os.path.normcase(item.repository_path) == normalized_key for item in existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Repository already registered"
        )

    role = request.repository_role
    if role is None:
        role = RepositoryRole.PRIMARY if not existing else RepositoryRole.UNKNOWN
    if role is RepositoryRole.PRIMARY and any(
        item.repository_role is RepositoryRole.PRIMARY for item in existing
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Project already has a primary repository"
        )

    now = datetime.now(timezone.utc)
    repository = ProjectRepository(
        project_id=project_id,
        local_user_id=current.user.id,
        repository_path=normalized_root,
        repository_name=Path(normalized_root).name,
        repository_role=role,
        vcs_type=VcsType.GIT,
        default_branch=inspected.default_branch,
        current_branch=inspected.current_branch,
        last_commit_sha=inspected.last_commit_sha,
        is_dirty=bool(inspected.is_dirty),
        last_status_checked_at=now,
    )
    session.add(repository)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Repository registration conflicts"
        ) from error
    return _repository_view(repository)


@router.get("/projects/{project_id}/repositories", response_model=list[ProjectRepositoryView])
def list_repositories(
    project_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> list[ProjectRepositoryView]:
    _get_owned_project(session, project_id, current.user.id)
    repositories = session.scalars(
        select(ProjectRepository)
        .where(ProjectRepository.project_id == project_id, ProjectRepository.archived_at.is_(None))
        .order_by(ProjectRepository.created_at)
    )
    return [_repository_view(repository) for repository in repositories]


@router.get("/repositories/{repository_id}/status", response_model=RepositoryStatusView)
def get_repository_status(
    repository_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> RepositoryStatusView:
    repository = _get_owned_repository(session, repository_id, current.user.id)
    return _status_view(repository)


@router.post("/repositories/{repository_id}/refresh-status", response_model=RepositoryStatusView)
def refresh_repository_status(
    repository_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> RepositoryStatusView:
    repository = _get_owned_repository(session, repository_id, current.user.id)
    inspected = inspect_git_repository(repository.repository_path)
    if inspected.is_git_repository and not inspected.error_code:
        repository.repository_path = inspected.repository_root or repository.repository_path
        repository.default_branch = inspected.default_branch
        repository.current_branch = inspected.current_branch
        repository.last_commit_sha = inspected.last_commit_sha
        repository.is_dirty = bool(inspected.is_dirty)
        repository.last_status_checked_at = datetime.now(timezone.utc)
        session.commit()
    return _status_view(repository, inspected)
