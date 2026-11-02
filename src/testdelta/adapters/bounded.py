"""Put a wall-clock boundary around the mutation provider's CPU work."""

import json
import os
import subprocess
import sys
from pathlib import Path


def generate_bounded(workspace: Path, sources: list[str], maximum: int, timeout: float) -> list[dict]:
    tool_src = str(Path(__file__).resolve().parents[2])
    environment = dict(os.environ)
    environment["PYTHONPATH"] = tool_src
    process = subprocess.run(
        [sys.executable, "-m", "testdelta.adapters.worker"],
        input=json.dumps({"workspace": str(workspace), "source_modules": sources,
                          "max_mutants": maximum}),
        text=True, capture_output=True, env=environment, timeout=timeout, check=True,
    )
    return json.loads(process.stdout)
