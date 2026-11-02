"""Put a wall-clock boundary around the mutation provider's CPU work."""

import json
import os
import subprocess
import sys
from pathlib import Path


def generate_bounded(workspace: Path, sources: list[str], maximum: int, timeout: float) -> list[dict]:
    tool_src = str(Path(__file__).resolve().parents[2])
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    process = subprocess.run(
        # Isolate from the caller's cwd and Python environment, then add only
        # the supervisor's own package location (also supports source checkouts).
        [sys.executable, "-I", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); "
         "from testdelta.adapters.worker import main; main()", tool_src],
        input=json.dumps({"workspace": str(workspace), "source_modules": sources,
                          "max_mutants": maximum}),
        text=True, capture_output=True, env=environment, timeout=timeout, check=True,
    )
    return json.loads(process.stdout)
