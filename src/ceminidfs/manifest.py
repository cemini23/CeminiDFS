from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from ceminidfs.config import PROJECT_ROOT


@dataclass
class RunManifest:
    run_id: str
    git_commit: str = ""
    config_sha256: str = ""
    input_artifacts: Dict[str, Any] = field(default_factory=dict)
    stage_status: Dict[str, str] = field(default_factory=dict)
    random_seed: Optional[int] = None

    def write(self, path: Union[str, Path]) -> None:
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "RunManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**payload)

    def record_stage(self, name: str, status: str) -> None:
        self.stage_status[name] = status

    def record_artifact(self, name: str, path: Union[str, Path]) -> None:
        artifacts = self.input_artifacts.setdefault("artifacts", {})
        artifacts[name] = str(path)


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=PROJECT_ROOT,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def config_sha256(config: Mapping[str, Any]) -> str:
    payload = json.dumps(_jsonable(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
