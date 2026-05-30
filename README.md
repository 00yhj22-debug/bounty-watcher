# bounty-watcher

A 30-minute cron that searches GitHub for freshly-posted bounty issues (Algora and Polar.sh by default) and sends an alert to a Telegram chat.

## What it does

Every 30 minutes a GitHub Actions job runs `bounty_watcher.py`, which:

1. Searches the GitHub issue index for issues created in the last 3 hours that carry any of the watched bounty labels (`💎 Bounty` for Algora, `Polar` for Polar.sh), are still open, and have no assignee. Results from each label are merged and deduplicated.
2. Filters the candidates: skips known bounty-farm orgs, repos under 200 stars, archived repos, and languages outside Python / TypeScript / JavaScript / Go / Rust.
3. Cross-checks each remaining issue against `state.json` so the same alert never fires twice.
4. Sends a one-line Telegram message — source, amount, repo, title, URL — for each surviving issue.

`state.json` is committed back to the repo at the end of each run so the dedup memory persists across cron ticks.

## Tuning without code changes

The three filter knobs can be overridden via environment variables on the workflow:

| Env var          | Default          | Notes                                          |
|------------------|------------------|------------------------------------------------|
| `BOUNTY_LABELS`  | `💎 Bounty,Polar`| Comma-separated label list to search           |
| `MIN_STARS`      | `200`            | Reject repos under this star count             |
| `LOOKBACK_HOURS` | `3`              | How far back to look on each tick              |

## Secrets used

- `GH_TOKEN` — personal access token used for the GitHub search and repo lookups (`public_repo` is enough for the read paths, the workflow uses the default `GITHUB_TOKEN` for `state.json` commits via `permissions: contents: write`).
- `TG_TOKEN` — Telegram Bot API token from BotFather.
- `TG_CHAT` — Telegram chat id to post into.

## Manually trigger

Use the **Run workflow** button on the [Actions tab](../../actions) (the workflow has `workflow_dispatch:` enabled).
