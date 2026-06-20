from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union


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
