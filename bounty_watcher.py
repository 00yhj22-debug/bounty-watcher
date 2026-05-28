"""Watch GitHub for newly-posted Algora bounties and ping Telegram."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

GH_TOKEN = os.environ["GH_TOKEN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT = os.environ["TG_CHAT"]

STATE_FILE = Path(__file__).resolve().parent / "state.json"

# Orgs we've already decided not to chase — bounty farms, interview reservations,
# CTF-style training repos, etc.  Add more here as we encounter them.
BLACKLIST_ORGS = {
    "archestra-ai",
    "mergeos-bounties",
    "SecureBananaLabs",
}

# Languages where our Python/TypeScript-heavy stack actually has an edge.
ALLOWED_LANGUAGES = {"Python", "TypeScript", "JavaScript", "Go", "Rust"}

# Star floor to keep tiny "issue farm" repos out of the alert stream.
MIN_STARS = 200

# Algora's standard bounty label (with the diamond emoji).
BOUNTY_LABEL = "💎 Bounty"

# How far back to look on each tick — generous because GitHub Actions cron
# can slip 10–15 minutes during peak hours.
LOOKBACK_HOURS = 3

USER_AGENT = "bounty-watcher (github.com/00yhj22-debug/bounty-watcher)"


def gh_request(url: str, params: dict[str, str] | None = None) -> dict:
    """GET a GitHub API endpoint and decode the JSON response."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def telegram_send(text: str) -> dict:
    """Send a plain-text message to the configured Telegram chat."""
    data = urllib.parse.urlencode(
        {
            "chat_id": TG_CHAT,
            "text": text,
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def parse_amount(labels: list[str]) -> int | None:
    """Pull the dollar amount out of an Algora-style ``$NNN`` label."""
    for name in labels:
        if name.startswith("$"):
            digits = "".join(c for c in name[1:] if c.isdigit())
            if digits:
                return int(digits)
    return None


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seen": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def search_recent_bounty_issues() -> list[dict]:
    """Issues with the Algora bounty label opened in the lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    # GitHub now rejects search/issues queries that don't pin the type with
    # ``is:issue`` or ``is:pull-request``.  We only want issues here.
    q = (
        f'is:issue label:"{BOUNTY_LABEL}" state:open no:assignee '
        f"created:>{cutoff_str}"
    )
    data = gh_request(
        "https://api.github.com/search/issues",
        {"q": q, "sort": "created", "order": "desc", "per_page": "30"},
    )
    return data.get("items", []) or []


def repo_meets_bar(repo: dict) -> bool:
    """True if the repo is worth pinging on."""
    if repo.get("archived"):
        return False
    if repo.get("language") not in ALLOWED_LANGUAGES:
        return False
    if repo.get("stargazers_count", 0) < MIN_STARS:
        return False
    return True


def format_alert(issue: dict, repo: dict) -> str:
    labels = [label["name"] for label in issue.get("labels", [])]
    amount = parse_amount(labels)
    amount_str = f"${amount}" if amount is not None else "?"
    return (
        f"💎 New bounty {amount_str}\n"
        f"{repo['full_name']} ({repo['stargazers_count']}⭐, "
        f"{repo.get('language') or '?'})\n"
        f"{issue['title']}\n"
        f"{issue['html_url']}"
    )


def main() -> int:
    state = load_state()
    seen_ids = set(state.get("seen", []))

    issues = search_recent_bounty_issues()
    print(f"candidate issues: {len(issues)}", flush=True)

    sent_any = False
    for issue in issues:
        issue_id = issue["id"]
        if issue_id in seen_ids:
            continue
        # ``search/issues`` returns PRs too — skip them.
        if issue.get("pull_request"):
            seen_ids.add(issue_id)
            continue

        repo_url = issue.get("repository_url", "")
        owner = repo_url.split("/repos/")[-1].split("/")[0]
        if owner in BLACKLIST_ORGS:
            seen_ids.add(issue_id)
            continue

        try:
            repo = gh_request(repo_url)
        except Exception as exc:
            print(f"repo fetch failed for {repo_url}: {exc}", flush=True)
            continue

        if not repo_meets_bar(repo):
            seen_ids.add(issue_id)
            continue

        message = format_alert(issue, repo)
        try:
            telegram_send(message)
        except Exception as exc:
            print(f"telegram send failed: {exc}", file=sys.stderr)
            continue

        print(f"alerted: {repo['full_name']}#{issue['number']}", flush=True)
        seen_ids.add(issue_id)
        sent_any = True

    # Cap the seen list so the state file stays small.
    state["seen"] = sorted(seen_ids)[-500:]
    save_state(state)

    if not sent_any:
        print("no new alertable bounties", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
