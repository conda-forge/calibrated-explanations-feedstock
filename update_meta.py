"""Bump recipe/meta.yaml to the latest PyPI release and open a PR upstream.

Usage: python update_meta.py [--dry-run]

Requires the ``gh`` CLI authenticated against an account with push access to
this fork (``origin``) and permission to open PRs against ``UPSTREAM_REPO``.

Behavior:
  1. Fetch the latest version + sdist sha256 from PyPI.
  2. If recipe/meta.yaml is already current, do nothing and exit 0.
  3. Otherwise branch from upstream/main, rewrite meta.yaml (version, sha256,
     build number reset to 0), commit, push to origin, and open (or reuse) a
     PR against UPSTREAM_REPO. The fork's own default branch is never touched.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import requests

PYPI_PROJECT = "calibrated-explanations"
UPSTREAM_OWNER = "conda-forge"
UPSTREAM_REPO_NAME = "calibrated-explanations-feedstock"
UPSTREAM_URL = f"https://github.com/{UPSTREAM_OWNER}/{UPSTREAM_REPO_NAME}.git"
UPSTREAM_SLUG = f"{UPSTREAM_OWNER}/{UPSTREAM_REPO_NAME}"

REPO_ROOT = Path(__file__).resolve().parent
META_PATH = REPO_ROOT / "recipe" / "meta.yaml"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_ROOT, check=True, text=True, **kwargs)


def capture(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def fetch_latest_release() -> tuple[str, str]:
    response = requests.get(f"https://pypi.org/pypi/{PYPI_PROJECT}/json", timeout=30)
    response.raise_for_status()
    data = response.json()
    latest_version = data["info"]["version"]

    for file_info in data["releases"][latest_version]:
        if file_info["filename"].endswith(".tar.gz"):
            return latest_version, file_info["digests"]["sha256"]
    raise ValueError(f"Could not find an sdist sha256 for {latest_version} on PyPI")


def current_recipe_version() -> str:
    meta_content = META_PATH.read_text(encoding="utf-8")
    match = re.search(r'{% set version = "(.*?)" %}', meta_content)
    if not match:
        raise ValueError("Could not find the current version in recipe/meta.yaml")
    return match.group(1)


def write_recipe(version: str, sha256_hash: str) -> None:
    meta_content = META_PATH.read_text(encoding="utf-8")
    meta_content = re.sub(
        r'{% set version = ".*?" %}', f'{{% set version = "{version}" %}}', meta_content
    )
    meta_content = re.sub(r"sha256: .*", f"sha256: {sha256_hash}", meta_content)
    meta_content = re.sub(r"(\bnumber:\s*)\d+", r"\g<1>0", meta_content)
    META_PATH.write_text(meta_content, encoding="utf-8")


def ensure_upstream_remote() -> None:
    remotes = capture(["git", "remote"]).splitlines()
    if "upstream" not in remotes:
        run(["git", "remote", "add", "upstream", UPSTREAM_URL])


def fork_owner() -> str:
    origin_url = capture(["git", "remote", "get-url", "origin"])
    match = re.search(r"github\.com[:/]([^/]+)/", origin_url)
    if not match:
        raise ValueError(f"Could not parse fork owner from origin URL: {origin_url}")
    return match.group(1)


def existing_pr_url(head: str) -> str | None:
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--repo", UPSTREAM_SLUG,
            "--head", head,
            "--state", "open",
            "--json", "url",
        ],
        cwd=REPO_ROOT, text=True, capture_output=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("gh pr list failed; is `gh auth status` logged in?")
    prs = json.loads(result.stdout or "[]")
    return prs[0]["url"] if prs else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without touching git or opening a PR.",
    )
    args = parser.parse_args()

    latest_version, sha256_hash = fetch_latest_release()
    current_version = current_recipe_version()

    if current_version == latest_version:
        print(f"recipe/meta.yaml already at {current_version}; nothing to do.")
        return 0

    print(f"PyPI has {latest_version} (recipe currently at {current_version}).")
    if args.dry_run:
        print(f"[dry-run] would branch, update meta.yaml, commit, push, and open a PR "
              f"against {UPSTREAM_SLUG}.")
        return 0

    status = capture(["git", "status", "--porcelain"])
    if status:
        print("ERROR: feedstock working tree is not clean; refusing to touch it.\n"
              f"{status}", file=sys.stderr)
        return 1

    original_branch = capture(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = f"update-v{latest_version}"
    owner = fork_owner()
    head = f"{owner}:{branch}"

    try:
        ensure_upstream_remote()
        run(["git", "fetch", "upstream", "main"])
        run(["git", "checkout", "-B", branch, "upstream/main"])

        write_recipe(latest_version, sha256_hash)

        diff = capture(["git", "status", "--porcelain"])
        if not diff:
            print("No effective changes after rewrite; nothing to commit.")
            return 0

        run(["git", "add", "recipe/meta.yaml"])
        run(["git", "commit", "-m", f"v{latest_version}"])
        run(["git", "push", "--force-with-lease", "origin", f"{branch}:{branch}"])

        pr_url = existing_pr_url(head)
        if pr_url:
            print(f"PR already open: {pr_url}")
        else:
            run([
                "gh", "pr", "create",
                "--repo", UPSTREAM_SLUG,
                "--base", "main",
                "--head", head,
                "--title", f"v{latest_version}",
                "--body", f"Automated version bump to {latest_version} "
                          "(sha256 refreshed from PyPI, build number reset to 0).",
            ])
    finally:
        subprocess.run(["git", "checkout", original_branch], cwd=REPO_ROOT, text=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
