#!/usr/bin/env python3
import sys
import os
import json
import time
import subprocess
from pathlib import Path

# =====================================================
#  IMPORT UPDATE MANAGER HELPERS
# =====================================================
from worker_update import preview_update, request_update


BASE_DIR = Path(__file__).resolve().parent.parent


# =====================================================
# LOG HELPER (sends log messages to Electron UI)
# =====================================================
def log(msg):
    sys.stdout.write(json.dumps({"log": str(msg)}) + "\n")
    sys.stdout.flush()


# =====================================================
# RUN SHELL COMMAND
# =====================================================
def run_cmd(cmd, cwd=None, timeout=300):
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True
        )
        return {
            "ok": p.returncode == 0,
            "code": p.returncode,
            "output": p.stdout
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =====================================================
# PARSE FILE BLOCKS FROM TEXT
# =====================================================
def parse_text_for_files(text: str):
    """
    Extract blocks of the form:
    path/to/file.py:
    ```
    content here
    ```
    """
    import re

    pattern = re.compile(
        r'(?:^|\n)([\w\-\./]+)\s*:\s*```[a-zA-Z0-9+\-]*\n([\s\S]*?)\n```'
    )

    files = []
    for m in pattern.finditer(text):
        filename = m.group(1).strip()
        content = m.group(2)
        files.append({"filename": filename, "content": content})

    return files


# =====================================================
# CREATE PROJECT FOLDER FROM TEXT
# =====================================================
def create_project_from_text(text):
    files = parse_text_for_files(text)
    if not files:
        return {"ok": False, "error": "No file blocks found in text."}

    out_dir = BASE_DIR / f"project_{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        path = out_dir / f["filename"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f["content"], encoding="utf-8")

    return {
        "ok": True,
        "project_dir": str(out_dir),
        "file_count": len(files)
    }


# =====================================================
# INSTALL PYTHON DEPENDENCIES (venv + pip install)
# =====================================================
def install_python_deps(proj_dir: Path):
    venv = proj_dir / ".venv"
    run_cmd(f"python -m venv {venv}")

    pip_path = (
        venv / "Scripts" / "pip.exe"
        if os.name == "nt"
        else venv / "bin" / "pip"
    )

    if not pip_path.exists():
        return {"ok": False, "error": "pip not found in virtualenv"}

    req = proj_dir / "requirements.txt"
    if req.exists():
        return run_cmd(f"\"{pip_path}\" install -r \"{req}\"")
    return {"ok": True, "msg": "No requirements.txt found"}


# =====================================================
# INSTALL NODE DEPENDENCIES (npm install)
# =====================================================
def install_node_deps(proj_dir: Path):
    pkg = proj_dir / "package.json"
    if not pkg.exists():
        return {"ok": True, "msg": "No package.json found"}
    return run_cmd("npm install", cwd=str(proj_dir))


# =====================================================
# PROCESS INCOMING MESSAGE FROM ELECTRON
# =====================================================
def handle_message(obj):
    cmd = obj.get("cmd")

    # -------------------------------------------------------
    # BUILD FROM TEXT
    # -------------------------------------------------------
    if cmd == "build_from_text":
        text = obj.get("text", "")
        log("Starting build_from_text...")

        res = create_project_from_text(text)
        if not res["ok"]:
            return res

        proj = Path(res["project_dir"])
        steps = []

        # Python install
        if (proj / "requirements.txt").exists():
            log("Installing Python dependencies...")
            py_res = install_python_deps(proj)
            steps.append(py_res)

        # Node install
        if (proj / "package.json").exists():
            log("Installing Node dependencies...")
            node_res = install_node_deps(proj)
            steps.append(node_res)

        log("Build complete")

        return {"ok": True, "project_dir": str(proj), "steps": steps}

    # -------------------------------------------------------
    # PREVIEW AI UPDATE (NO FILE WRITE)
    # -------------------------------------------------------
    elif cmd == "preview_update":
        req = obj.get("request", "")
        key = obj.get("openai_key", "")
        return preview_update(req, key)

    # -------------------------------------------------------
    # RUN FULL AI UPDATE (PATCH + PR)
    # -------------------------------------------------------
    elif cmd == "request_update":
        req = obj.get("request", "")
        openai_key = obj.get("openai_key", "")
        gh_token = obj.get("gh_token", "")
        gh_owner = obj.get("gh_owner", "")
        gh_repo = obj.get("gh_repo", "")

        return request_update(
            request_text=req,
            openai_key=openai_key,
            gh_token=gh_token,
            gh_owner=gh_owner,
            gh_repo=gh_repo
        )

    # -------------------------------------------------------
    # UNKNOWN COMMAND
    # -------------------------------------------------------
    else:
        return {"ok": False, "error": f"Unknown command: {cmd}"}


# =====================================================
# MAIN LOOP — LISTEN FOR ELECTRON MESSAGES
# =====================================================
def main():
    log("Python backend started")

    for line in sys.stdin:
        if not line.strip():
            continue

        try:
            obj = json.loads(line)
        except:
            log("Invalid JSON received")
            continue

        try:
            res = handle_message(obj)
        except Exception as e:
            res = {
                "ok": False,
                "error": str(e)
            }

        # return the __id to match Electron request
        if "__id" in obj:
            res["__id"] = obj["__id"]

        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
