"""Resolve Linux/Python dependencies without copying secrets into build contexts.

Run in the Python base image with pip-tools installed and a read-only repo mount.
Stdout is a JSON mapping; the caller saves the reviewed requirements.lock files.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SERVICES = ("catalog", "telemetry", "production", "simulator", "maintenance")


def main():
    root = Path(__file__).resolve().parents[1]
    locks = {}
    services = sys.argv[1:] or SERVICES
    unknown = set(services) - set(SERVICES)
    if unknown:
        raise SystemExit(f"Unknown service(s): {', '.join(sorted(unknown))}")
    with tempfile.TemporaryDirectory() as temporary:
        for service in services:
            output = Path(temporary) / f"{service}.lock"
            env = {
                **os.environ,
                "CUSTOM_COMPILE_COMMAND": "python scripts/lock_requirements.py",
            }
            subprocess.run(
                [
                    sys.executable, "-m", "piptools", "compile",
                    "--quiet", "--strip-extras",
                    "--no-emit-index-url", "--no-emit-trusted-host",
                    "--output-file", str(output),
                    str(root / "services" / service / "requirements.txt"),
                ],
                check=True, env=env,
            )
            locks[f"services/{service}/requirements.lock"] = output.read_text()
    print("LOCK_OUTPUT=" + json.dumps(locks))


if __name__ == "__main__":
    main()
