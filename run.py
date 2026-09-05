#!/usr/bin/env python3
"""
Nidhi's Budget Tracker
----------------------
Run with:   python run.py
Docker:     docker-compose up --build

Access the dashboard at: http://localhost:8501
Neo4j Browser at:        http://localhost:7474
"""
import subprocess
import sys
import os
from pathlib import Path


def main():
    project_root = Path(__file__).parent.resolve()
    os.chdir(project_root)

    # Copy .env.example -> .env if .env doesn't exist
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text())
        print("Created .env from .env.example — edit it if your Neo4j credentials differ.\n")

    print("=" * 55)
    print("  Nidhi's Budget Tracker")
    print("=" * 55)
    print("  Dashboard  →  http://localhost:8501")
    print("  Neo4j      →  http://localhost:7474")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    print()

    result = subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run",
            str(project_root / "app" / "main.py"),
            "--server.address=0.0.0.0",
            "--server.port=8501",
            "--browser.gatherUsageStats=false",
        ]
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
