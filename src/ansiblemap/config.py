from dataclasses import dataclass
import os


@dataclass(slots=True)
class Settings:
    database_url: str
    bitbucket_deployment: str
    bitbucket_base_url: str
    bitbucket_workspace: str | None
    bitbucket_token: str | None
    bitbucket_username: str | None
    bitbucket_app_password: str | None
    bitbucket_password: str | None
    project_playbooks: str | None
    project_roles: str | None
    project_collections: str | None
    request_timeout_seconds: float = 30.0
    max_files_per_repo: int = 2000
    max_file_size_bytes: int = 1048576


    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url:
            raise ValueError("DATABASE_URL is required")

        return cls(
            database_url=database_url,
            bitbucket_deployment=os.getenv("BITBUCKET_DEPLOYMENT", "cloud").strip().lower(),
            bitbucket_base_url=os.getenv("BITBUCKET_BASE_URL", "https://api.bitbucket.org/2.0"),
            bitbucket_workspace=os.getenv("BITBUCKET_WORKSPACE"),
            bitbucket_token=os.getenv("BITBUCKET_TOKEN"),
            bitbucket_username=os.getenv("BITBUCKET_USERNAME"),
            bitbucket_app_password=os.getenv("BITBUCKET_APP_PASSWORD"),
            bitbucket_password=os.getenv("BITBUCKET_PASSWORD"),
            project_playbooks=os.getenv("BITBUCKET_PROJECT_PLAYBOOKS"),
            project_roles=os.getenv("BITBUCKET_PROJECT_ROLES"),
            project_collections=os.getenv("BITBUCKET_PROJECT_COLLECTIONS"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            max_files_per_repo=int(os.getenv("MAX_FILES_PER_REPO", "2000")),
            max_file_size_bytes=int(os.getenv("MAX_FILE_SIZE_BYTES", str(1024 * 1024))),
        )
