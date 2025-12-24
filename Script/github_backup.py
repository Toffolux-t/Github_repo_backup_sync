#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import List


LOG_FILE_NAME = "github_backup.log"


def log(msg: str):
    """Print to console and append to the log file with timestamp."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{now}] {msg}"
    print(line)
    with open(LOG_FILE_NAME, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_cmd(cmd: List[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a system command and return the CompletedProcess."""
    log(f"Running command: {' '.join(cmd)} (cwd={cwd})")
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stdout:
        log(f"STDOUT: {result.stdout.strip()}")
    if result.stderr:
        log(f"STDERR: {result.stderr.strip()}")
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)} (return code={result.returncode})"
        )
    return result


def get_authenticated_user() -> str:
    """Return the GitHub username of the currently authenticated gh user."""
    log("Retrieving authenticated user from gh...")
    try:
        result = run_cmd(["gh", "api", "user", "--jq", ".login"], check=True)
        user = result.stdout.strip()
        if not user:
            raise RuntimeError("Could not retrieve GitHub user from gh.")
        log(f"Authenticated user: {user}")
        return user
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)


def get_all_repos_for_user(user: str) -> List[dict]:
    """
    Retrieve all repositories (public and private) accessible to the user.

    Uses the 'user/repos' API via gh with --paginate.
    Filters out archived repositories.
    """
    log(f"Retrieving repository list for user {user} via gh api user/repos...")
    repos: List[dict] = []

    cmd = [
        "gh",
        "api",
        "user/repos",
        "--paginate",
        "--jq",
        ".[] | {name:.name, full_name:.full_name, ssh_url:.ssh_url, clone_url:.clone_url, archived:.archived}",
    ]

    result = run_cmd(cmd, check=True)
    lines = result.stdout.strip().splitlines()
    for line in lines:
        try:
            repo = json.loads(line)
            if not repo.get("archived", False):
                repos.append(repo)
        except json.JSONDecodeError:
            # Ignore invalid or empty lines
            continue

    log(f"Found {len(repos)} non-archived repositories.")
    return repos


def clone_or_update_repo(repo: dict, base_dir: Path, use_ssh: bool = False):
    """
    Clone or update a single repository.

    - base_dir: directory where repositories are stored.
    - use_ssh: if True, use ssh_url; otherwise use clone_url (HTTPS).
    """
    full_name = repo["full_name"]   # e.g. "R0mb0/my-repo"
    name = repo["name"]             # e.g. "my-repo"
    ssh_url = repo["ssh_url"]
    clone_url = repo["clone_url"]
    url = ssh_url if use_ssh else clone_url

    repo_dir = base_dir / name

    if not repo_dir.exists():
        # Clone from scratch
        log(f"New repository detected: {full_name}. Cloning into {repo_dir}...")
        try:
            run_cmd(["git", "clone", url, str(repo_dir)], check=True)
            log(f"Successfully cloned: {full_name}")
        except Exception as e:
            log(f"ERROR while cloning {full_name}: {e}")
    else:
        # Update existing repository
        log(f"Repository already present: {full_name}. Checking for updates...")
        try:
            # Fetch all remotes and prune deleted branches
            run_cmd(["git", "fetch", "--all", "--prune"], cwd=repo_dir, check=True)
            # Pull latest changes for the current branch (best-effort)
            run_cmd(["git", "pull"], cwd=repo_dir, check=False)
            log(f"Updated repository: {full_name}")
        except Exception as e:
            log(f"ERROR while updating {full_name}: {e}")


def main():
    # Working directory is where the script is executed
    base_dir = Path.cwd()
    log(f"=== Starting GitHub backup in directory: {base_dir} ===")

    # Ensure git and gh are available
    for cmd_name in ("git", "gh"):
        if not shutil.which(cmd_name):
            log(
                f"ERROR: '{cmd_name}' command not found in PATH. "
                f"Please install it before running this script."
            )
            sys.exit(1)

    user = get_authenticated_user()
    repos = get_all_repos_for_user(user)

    # Set to True if you prefer to use SSH instead of HTTPS
    use_ssh = False

    for repo in repos:
        clone_or_update_repo(repo, base_dir=base_dir, use_ssh=use_ssh)

    log("=== Backup completed. ===")


if __name__ == "__main__":
    main()