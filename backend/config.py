"""Explicitly injected backend settings; no environment or dotenv loading.

Validation checks directory metadata/usability now. The repository-access
service enforces authorization, identity and containment again at time of use.
No provider credentials belong in this phase's configuration.
"""

from __future__ import annotations

import ipaddress
import os
import stat
import unicodedata
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigurationError(ValueError):
    """Controlled configuration-policy failure, without host paths or values."""


class BackendConfig(BaseModel):
    """Immutable local-only settings; repository access is denied by default."""

    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, validate_default=True,
        hide_input_in_errors=True, revalidate_instances="always",
    )

    bind_host: Annotated[str, Field(min_length=1, max_length=45)] = "127.0.0.1"
    bind_port: Annotated[int, Field(ge=1, le=65535)] = 8000
    permitted_repository_roots: tuple[Path, ...] = Field(default=(), repr=False, exclude=True)
    storage_directory: Path | None = Field(default=None, repr=False, exclude=True)
    max_stored_analyses: Annotated[int, Field(ge=1, le=4096)] = 256
    max_stored_analysis_bytes: Annotated[int, Field(ge=1024, le=64 * 1024 * 1024)] = 16 * 1024 * 1024
    max_request_body_bytes: Annotated[int, Field(ge=1, le=16 * 1024 * 1024)] = 1024 * 1024
    scan_workers: Annotated[int, Field(ge=1, le=4)] = 1
    job_workers: Annotated[int, Field(ge=1, le=8)] = 2
    max_queued_jobs: Annotated[int, Field(ge=1, le=256)] = 32
    max_jobs: Annotated[int, Field(ge=1, le=2048)] = 128
    max_benchmark_units: Annotated[int, Field(ge=1, le=1024)] = 256
    max_job_result_bytes: Annotated[int, Field(ge=1024, le=8 * 1024 * 1024)] = 1024 * 1024
    benchmark_registry_path: Path | None = Field(default=None, repr=False, exclude=True)
    benchmark_recordings_path: Path | None = Field(default=None, repr=False, exclude=True)
    permitted_benchmark_data_roots: tuple[Path, ...] = Field(default=(), repr=False, exclude=True)
    benchmark_approval_manifest_path: Path | None = Field(default=None, repr=False, exclude=True)
    max_concurrent_provider_requests: Annotated[int, Field(ge=1, le=16)] = 4
    max_requests_per_job: Annotated[int, Field(ge=1, le=1024)] = 64
    max_output_tokens: Annotated[int, Field(ge=1, le=8192)] = 1024
    max_provider_response_bytes: Annotated[int, Field(ge=1, le=8 * 1024 * 1024)] = 1024 * 1024
    scan_timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 30
    provider_timeout_seconds: Annotated[int, Field(ge=1, le=120)] = 30
    job_timeout_seconds: Annotated[int, Field(ge=1, le=1800)] = 300
    job_retention_seconds: Annotated[int, Field(ge=1, le=604800)] = 86400

    @field_validator("bind_host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        if "%" in value:
            raise ValueError("Scoped bind addresses are outside the initial local-only policy.")
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise ValueError("Bind host must be a numeric loopback address.") from None
        if not address.is_loopback:
            raise ValueError("Remote binding is outside the initial local-only policy.")
        return str(address)

    @field_validator("permitted_repository_roots", "permitted_benchmark_data_roots", mode="before")
    @classmethod
    def usable_roots(cls, value: object) -> tuple[Path, ...]:
        if type(value) not in (tuple, list) or len(value) > 16:
            raise ValueError("Permitted roots must be an explicit array of at most 16 directories.")
        roots: list[Path] = []
        for item in value:
            if not isinstance(item, (str, Path)):
                raise ValueError("Each permitted root must be an absolute local directory path.")
            if isinstance(item, str) and (
                not item or item.startswith("\\\\") or "\x00" in item
                or any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in item)
            ):
                raise ValueError("Permitted roots require ordinary local directory paths.")
            try:
                path = Path(item)
                if any(unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"} for char in str(path)):
                    raise ValueError("Permitted roots cannot contain control characters or invalid Unicode.")
                if not path.is_absolute() or path == Path(path.anchor) or str(path).startswith("\\\\"):
                    raise ValueError("A permitted root must be an absolute local directory below a filesystem root.")
                before = path.lstat()
                if stat.S_ISLNK(before.st_mode) or (
                    getattr(before, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                ) or not stat.S_ISDIR(before.st_mode):
                    raise ValueError("A permitted root must be a directory without a final link or reparse point.")
                resolved = path.resolve(strict=True)
                if resolved == Path(resolved.anchor):
                    raise ValueError("A permitted root must remain below a filesystem root after resolution.")
                after = resolved.lstat()
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise ValueError("Permitted root identity changed during configuration validation.")
                with os.scandir(resolved):
                    pass  # Verify it can be opened; do not enumerate or read its contents.
            except (OSError, RuntimeError):
                raise ValueError("A permitted repository root is unavailable.") from None
            except ValueError:
                raise ValueError("A permitted repository root is invalid or unavailable.") from None
            if resolved in roots:
                raise ValueError("Permitted repository roots must not be duplicated.")
            roots.append(resolved)
        return tuple(roots)

    @field_validator("storage_directory", mode="before")
    @classmethod
    def usable_storage(cls, value: object) -> Path | None:
        if value is None:
            return None
        return cls.usable_roots([value])[0]

    @field_validator("benchmark_registry_path", "benchmark_recordings_path", "benchmark_approval_manifest_path", mode="before")
    @classmethod
    def explicit_local_asset(cls, value: object) -> Path | None:
        if value is None:
            return None
        try:
            if not isinstance(value, (str, Path)):
                raise ValueError()
            path = Path(value)
            if not path.is_absolute() or str(path).startswith(("\\\\", "//")) or path.suffix.lower() != ".json":
                raise ValueError()
            before = path.lstat()
            if stat.S_ISLNK(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400 or not stat.S_ISREG(before.st_mode):
                raise ValueError()
            resolved = path.resolve(strict=True)
            after = resolved.lstat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError()
            return resolved
        except (OSError, ValueError, RuntimeError):
            raise ValueError("A benchmark asset must be an explicit regular local JSON file.") from None

    @model_validator(mode="after")
    def consistent_limits(self) -> BackendConfig:
        if self.max_queued_jobs > self.max_jobs or self.job_workers > self.max_jobs:
            raise ValueError("Queue and worker limits cannot exceed the total job limit.")
        if self.provider_timeout_seconds > self.job_timeout_seconds:
            raise ValueError("A provider timeout cannot exceed the overall job timeout.")
        if self.storage_directory is not None and any(
            self.storage_directory.is_relative_to(root) for root in self.permitted_repository_roots
        ):
            raise ValueError("Storage must be outside every permitted repository root.")
        if any(path.is_relative_to(root) for path in (self.benchmark_registry_path, self.benchmark_recordings_path)
               if path is not None for root in self.permitted_repository_roots):
            raise ValueError("Trusted benchmark assets must be outside permitted scan roots.")
        if self.benchmark_approval_manifest_path is not None and any(
            self.benchmark_approval_manifest_path.is_relative_to(root)
            for root in (*self.permitted_repository_roots, *self.permitted_benchmark_data_roots)
        ):
            raise ValueError("Operator approval must be outside source and benchmark-data roots.")
        if self.storage_directory is not None and any(self.storage_directory.is_relative_to(root) for root in self.permitted_benchmark_data_roots):
            raise ValueError("Storage must be outside benchmark-data roots.")
        return self

    def require_repository_roots(self) -> tuple[Path, ...]:
        """Scan-service startup calls this before enabling repository access.

        This is a fail-closed policy precondition, not a path authorizer or an
        implementation of time-of-use containment.
        """
        if not self.permitted_repository_roots:
            raise ConfigurationError("Repository scanning requires an explicit permitted-root policy.")
        return self.permitted_repository_roots

    def safe_report(self) -> dict[str, object]:
        """Report limits and policy presence, excluding root paths and credentials."""
        return {
            **self.model_dump(mode="json"),
            "permitted_repository_root_count": len(self.permitted_repository_roots),
            "repository_scanning_configured": bool(self.permitted_repository_roots),
        }
