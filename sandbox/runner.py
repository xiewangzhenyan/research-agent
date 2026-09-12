"""Fixed runner image supervisor; the controller freezes then collects outputs.

The entire container is untrusted. All outputs/metadata are bounded and checked
again by the controller. This process holds no credentials or Docker access.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    Path("/work/outputs").mkdir(exist_ok=True)
    # Remove only the controller-created ownership marker; its presence never means completion.
    Path("/work/outputs/agent-output-init").unlink(missing_ok=True)
    # Isolated imports prevent uploaded files from shadowing installed modules.
    result = subprocess.run([sys.executable, "-I", "-B", "-c", sys.argv[1]], check=False)
    temporary = Path("/work/outputs/.execution-result.tmp")
    temporary.write_text(json.dumps({"exit_code": result.returncode}))
    os.replace(temporary, "/work/outputs/.execution-result.json")
    # Keep tmpfs mounted. Controller pauses all processes before reading files,
    # then kills the whole container and confirms termination before committing.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
