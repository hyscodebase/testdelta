"""Generate mutations in a deadline-supervised process; never execute target code."""

import json
import sys
from pathlib import Path

from testdelta.adapters.cosmic_ray import generate_mutations


def main() -> None:
    request = json.load(sys.stdin)
    mutations = generate_mutations(
        Path(request["workspace"]), request["source_modules"], request["max_mutants"]
    )
    json.dump(mutations, sys.stdout)


if __name__ == "__main__":
    main()
