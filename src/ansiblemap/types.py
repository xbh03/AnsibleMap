from dataclasses import dataclass, field
from typing import Any


ArtifactType = str
DependencyType = str


@dataclass(slots=True)
class ArtifactInput:
    external_key: str
    type: ArtifactType
    name: str
    path: str
    fingerprint: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DependencyInput:
    from_external_key: str
    to_external_key: str
    dep_type: DependencyType


@dataclass(slots=True)
class ScanResult:
    artifacts: list[ArtifactInput]
    dependencies: list[DependencyInput]
