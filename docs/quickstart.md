# Quickstart: start AIDLC Kit in your organisation

For the person setting it up (about an hour, once). PMs only need step 7.

**You need:** Python 3.12, Git, the GitHub CLI (`gh auth login` done), admin
rights on a new empty GitHub repository, and the GitHub usernames of your team.

1. **Create the repository** on GitHub (empty, default branch `main`), add your
   team as collaborators with Write access, and clone it. In VS Code, open it.

2. **Install the kit** so every VS Code terminal, task and assistant can find
   `aidlc`:
   ```bash
   pipx install "aidlc-kit[anthropic] @ git+https://github.com/gobokobok/aidlc-kit@v0.1.0"
   aidlc --help
   ```
   Use `[openai]` instead of `[anthropic]` for OpenAI, Azure or a local model;
   drop the extra if nobody records eval answers.

3. **Set up the repository** for the assistants your team uses
   (`copilot`, `claude`, `cursor`, `agents`, `vscode`; repeat the flag):
   ```bash
   aidlc init --assistant copilot --assistant vscode \
     --install "pip install 'aidlc-kit[anthropic] @ git+https://github.com/gobokobok/aidlc-kit@v0.1.0'"
   ```
   The `--install` line tells CI where to get the kit; it is not on PyPI.

4. **Put your team in `aidlc.yaml`.** Replace the example people with real
   GitHub usernames and roles (`pm`, `ops_reviewer`, `tech_reviewer`,
   `risk_reviewer`, `data_owner`, `engineer`, `kit_admin`). You need two PMs, one
   person per reviewer role and one engineer; one person may hold several roles.
   Add the model to the `eval:` block if you will record eval answers. Then:
   ```bash
   aidlc validate && aidlc sync-codeowners
   git add -A && git commit -m "Configure AIDLC Kit" && git push -u origin main
   ```

5. **Protect `main`** (Settings, Rules, New ruleset): require a pull request
   with 1 approval and code-owner review; require the checks `validate`, `eval`
   and `approvals_complete`; block deletion and force pushes. Let **GitHub
   Actions** bypass the pull-request rule so the `audit` job can append to
   `audit/log.jsonl` (organisations only; personal repositories need the deploy
   key described in [setup.md](setup.md)).

6. **Pages (optional).** Settings, Pages, Source: **GitHub Actions**, to publish
   the viewer site. Without it, delete `.github/workflows/aidlc-site.yml`, or
   that workflow shows a red cross after each merge.

7. **First feature.** In VS Code Copilot Chat (or Claude Code) type
   `/new-feature`; with no assistant, run **Terminal, Run Task, "AIDLC:
   /new-feature"**. Then follow [workflow.md](workflow.md).

Each person runs `gh auth login` once. To check everything works with your
team, follow the [testing guide](testing-guide.md).
