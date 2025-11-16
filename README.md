# AutoBuilder (Electron + Python)

This repo contains an Electron frontend and a Python backend worker that:
- builds projects from assistant file-block outputs
- offers an AI Update Manager (patch + create GitHub PR via OpenAI)

## Quick start (Windows)

1. Install Node.js (v20+): https://nodejs.org
2. Install Python 3.10+ and ensure `python` is on PATH.
3. In PowerShell:
   - `cd AutoBuilder/electron-app`
   - `npm install`
4. Install Python packages:
   - `cd AutoBuilder/python-worker`
   - `python -m pip install --user -r requirements.txt`
5. Run the app:
   - From `AutoBuilder/electron-app`: `npm run dev`
6. In the app: Tools → AI Update Manager

## How AI Update Manager works
- Enter your OpenAI key and GitHub token (stored locally in the UI session only)
- Preview patch (AI returns JSON)
- Create PR (applies patch locally and opens a PR on GitHub)
