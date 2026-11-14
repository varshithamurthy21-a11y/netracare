"""Start NetraCare (API + web app) with one command:  python run.py

API  -> http://127.0.0.1:8000  (interactive docs at /docs)
App  -> http://localhost:8501
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    env = os.environ.copy()
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8000"], cwd=ROOT, env=env)
    time.sleep(2)  # give the API a moment to create and seed the database
    ui = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "frontend/app.py", "--server.port", "8501"],
        cwd=ROOT, env=env)
    try:
        ui.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (ui, api):
            proc.terminate()


if __name__ == "__main__":
    main()
