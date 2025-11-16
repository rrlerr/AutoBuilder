import os
import json
import time
import re
import hashlib
import requests
from pathlib import Path

# ==============================
# CONSTANTS
# ==============================
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
GITHUB_API = "https://api.github.com"

# ==============================
# PROMPT TEMPLATE FOR AI UPDATE ENGINE
# ==============================
PROMPT_TEMPLATE = '''You are an expert software engineer. 
Your job is to provide MINIMAL, SAFE, INCREMENTAL UPDATES to the user's application.

You will receive:
1. A list of files in the repository with SHA256 hashes
2. A natural language request describing a feature to add

You MUST respond ONLY with VALID JSON using this structure:

{
  "version": "1.0",
  "summary": "Short summary of the update",
  "changes": [
    {
      "path": "electron-app/src/example.js",
      "action": "modify" | "create" | "delete",
      "content": "FULL file content when modify/create"
    }
  ],
  "tests": [
    {
      "command": "npm run test:node",
      "expect": "pass"
    }
  ],
  "pr_title": "Short title",
  "pr_body": "Clear explanation of the update"
}

RULES:
- NEVER rewrite the entire project.
- ONLY change what is necessary.
- Keep Electron <-> Python IPC formats stable.
- ALWAYS return strictly valid JSON.
- Keep patches small and focused.
'''

# ==============================
# REPO SUMMARY (file list + SHA256)
# ==============================
def compute_repo_summary(base_dir):
    summary = {}
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if "node_modules" in root:
                continue
            full_path = os.path.join(root, f)
            try:
                with open(full_path, "rb") as fh:
                    sha = hashlib.sha256(fh.read()).hexdigest()
                rel = os.path.relpath(full_path, base_dir).replace("\\", "/")
                summary[rel] = sha
            except:
                pass
    return summary


# ==============================
# CALL OPENAI
# ==============================
def call_openai(openai_key, repo_summary, user_request, model="gpt-4o", max_tokens=1500):
    headers = {
        "Authorization": f"Bearer {openai_key}",
        "Content-Type": "application/json"
    }

    messages = [
        {"role": "system", "content": PROMPT_TEMPLATE},
        {"role": "user", "content": json.dumps({
            "repo_summary": repo_summary,
            "request": user_request
        })}
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens
    }

    res = requests.post(OPENAI_CHAT_URL, headers=headers, json=payload, timeout=60)
    res.raise_for_status()

    data = res.json()

    # Get AI message text
    return data["choices"][0]["message"]["content"]


# ==============================
# EXTRACT JSON FROM AI RESPONSE
# ==============================
def parse_ai_response(text):
    m = re.search(r'{[\s\S]*}', text)
    if not m:
        raise ValueError("No JSON object found in AI response")
    return json.loads(m.group(0))


# ==============================
# APPLY PATCHES LOCALLY
# ==============================
def apply_changes(base_dir, changes, backup_dir=".ai_patch_backups"):
    backup_path = os.path.join(base_dir, backup_dir)
    os.makedirs(backup_path, exist_ok=True)

    results = []

    for ch in changes:
        rel = ch['path']
        action = ch.get('action', "modify")
        content = ch.get('content', "")

        full_path = os.path.join(base_dir, rel.replace("/", os.sep))

        # CREATE/MODIFY
        if action in ("create", "modify"):
            # backup old version
            if os.path.exists(full_path):
                with open(full_path, "rb") as fh:
                    old = fh.read()
                with open(os.path.join(backup_path, f"{os.path.basename(full_path)}.bak"), "wb") as fh:
                    fh.write(old)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as fh:
                fh.write(content)

            results.append({"path": rel, "status": "written"})

        # DELETE
        elif action == "delete":
            if os.path.exists(full_path):
                os.remove(full_path)
                results.append({"path": rel, "status": "deleted"})
            else:
                results.append({"path": rel, "status": "not_found"})

        else:
            results.append({"path": rel, "status": "unknown_action"})

    return results


# ==============================
# GITHUB HELPERS
# ==============================
def gh_headers(token):
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def ensure_branch(owner, repo, token, base_branch, new_branch):
    # get base SHA
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{base_branch}",
        headers=gh_headers(token)
    )
    r.raise_for_status()
    base_sha = r.json()["object"]["sha"]

    # create branch
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
        headers=gh_headers(token),
        json={"ref": f"refs/heads/{new_branch}", "sha": base_sha}
    )

    # if branch exists, ignore error
    return base_sha


def create_blobs(owner, repo, token, files):
    blob_map = {}
    for f in files:
        r = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/blobs",
            headers=gh_headers(token),
            json={"content": f["content"], "encoding": "utf-8"}
        )
        r.raise_for_status()
        blob_map[f["path"]] = r.json()["sha"]
    return blob_map


def create_tree_and_commit(owner, repo, token, base_sha, blob_map, commit_message):
    # get base tree
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/commits/{base_sha}",
        headers=gh_headers(token)
    )
    r.raise_for_status()
    base_tree = r.json()["tree"]["sha"]

    tree_items = []
    for path, sha in blob_map.items():
        tree_items.append({
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": sha
        })

    # new tree
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees",
        headers=gh_headers(token),
        json={"base_tree": base_tree, "tree": tree_items}
    )
    r.raise_for_status()
    new_tree_sha = r.json()["sha"]

    # create commit
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/commits",
        headers=gh_headers(token),
        json={"message": commit_message, "parents": [base_sha], "tree": new_tree_sha}
    )
    r.raise_for_status()
    return r.json()["sha"]


def update_branch(owner, repo, token, branch, new_commit_sha):
    r = requests.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{branch}",
        headers=gh_headers(token),
        json={"sha": new_commit_sha}
    )
    r.raise_for_status()


def create_pull_request(owner, repo, token, title, body, branch):
    r = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        headers=gh_headers(token),
        json={"title": title, "head": branch, "base": "main", "body": body}
    )
    return r


# ==============================
# PREVIEW UPDATE (no file writes)
# ==============================
def preview_update(request_text, openai_key):
    base = Path(__file__).resolve().parent.parent
    summary = compute_repo_summary(str(base))
    text = call_openai(openai_key, summary, request_text)
    js = parse_ai_response(text)
    return {"ok": True, "preview": js}


# ==============================
# FULL UPDATE (apply + PR)
# ==============================
def request_update(request_text, openai_key, gh_token, gh_owner, gh_repo):
    base = Path(__file__).resolve().parent.parent

    summary = compute_repo_summary(str(base))
    response_text = call_openai(openai_key, summary, request_text)
    js = parse_ai_response(response_text)

    changes = js.get("changes", [])
    pr_title = js.get("pr_title", "AI Update")
    pr_body = js.get("pr_body", "Auto-generated update")

    # apply changes locally
    apply_result = apply_changes(str(base), changes)

    # prepare GitHub commit
    files = [
        {"path": c["path"], "content": c["content"]}
        for c in changes if c.get("action") in ("create", "modify")
    ]

    new_branch = f"ai-update-{int(time.time())}"

    base_sha = ensure_branch(gh_owner, gh_repo, gh_token, "main", new_branch)
    blob_map = create_blobs(gh_owner, gh_repo, gh_token, files)
    new_commit_sha = create_tree_and_commit(gh_owner, gh_repo, gh_token, base_sha, blob_map, pr_title)
    update_branch(gh_owner, gh_repo, gh_token, new_branch, new_commit_sha)

    pr = create_pull_request(gh_owner, gh_repo, gh_token, pr_title, pr_body, new_branch)

    try:
        pr.raise_for_status()
        return {
            "ok": True,
            "pr_url": pr.json().get("html_url"),
            "summary": js.get("summary", ""),
            "applied": apply_result
        }
    except:
        return {
            "ok": False,
            "error": pr.text,
            "applied": apply_result
        }
