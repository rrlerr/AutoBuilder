import traceback
from pathlib import Path

from update_manager import (
    preview_update as _preview_update,
    request_update as _request_update
)


# ====================================================
#  PREVIEW UPDATE — only asks AI for JSON patch
# ====================================================
def preview_update(request_text: str, openai_key: str):
    """
    request_text: Feature request from the user
    openai_key: User's OpenAI API Key

    Returns: JSON with preview patch OR error
    """
    try:
        if not request_text.strip():
            return {"ok": False, "error": "Empty request_text"}

        if not openai_key.strip():
            return {"ok": False, "error": "Missing OpenAI key"}

        result = _preview_update(request_text, openai_key)
        return {
            "ok": True,
            "preview": result.get("preview")
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }


# ====================================================
#  REQUEST UPDATE — apply patch + create PR
# ====================================================
def request_update(request_text: str, openai_key: str, gh_token: str,
                   gh_owner: str, gh_repo: str):
    """
    request_text: Feature request from user
    openai_key: OpenAI API Key
    gh_token: GitHub PAT
    gh_owner: GitHub username or org
    gh_repo: GitHub repository name

    Returns:
      OK or error + PR link (if successful)
    """

    try:
        # Validate required inputs
        if not request_text.strip():
            return {"ok": False, "error": "Empty request_text"}

        if not openai_key.strip():
            return {"ok": False, "error": "Missing OpenAI key"}

        if not gh_token.strip():
            return {"ok": False, "error": "Missing GitHub token"}

        if not gh_owner.strip():
            return {"ok": False, "error": "Missing GitHub owner"}

        if not gh_repo.strip():
            return {"ok": False, "error": "Missing GitHub repo name"}

        # Execute patch + PR flow
        result = _request_update(
            request_text=request_text,
            openai_key=openai_key,
            gh_token=gh_token,
            gh_owner=gh_owner,
            gh_repo=gh_repo
        )

        return result

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }
