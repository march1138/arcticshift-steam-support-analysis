#!/usr/bin/env python3
"""Collect archived subreddit threads from the Arctic Shift API.

This script does NOT access reddit.com or Reddit's Data API. It queries the
independent Arctic Shift archive and writes one JSON object per post/thread.
The collector deliberately makes no semantic judgments about the content.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API_BASE = "https://arctic-shift.photon-reddit.com/api"
USER_AGENT = "arcticshift-steam-support-analysis/0.2.0"
POST_LIMIT = 100
COMMENT_TREE_LIMIT = 9999


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_get(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any],
    delay: float,
    max_retries: int = 5,
) -> dict[str, Any]:
    url = f"{API_BASE}{endpoint}"

    for _ in range(max_retries):
        response = session.get(url, params=params, timeout=60)

        if response.status_code == 429:
            raw = response.headers.get("X-RateLimit-Reset")
            try:
                wait = max(float(raw), delay) if raw else max(5.0, delay)
            except ValueError:
                wait = max(5.0, delay)

            print(f"Rate limited; waiting {wait:.1f}s...")
            time.sleep(wait)
            continue

        response.raise_for_status()
        payload = response.json()
        time.sleep(delay)

        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected response from {endpoint}")

        return payload

    raise RuntimeError(f"Exceeded retry limit for {endpoint}")


def pseudonymizer(op_author: Any):
    mapping: dict[str, str] = {}
    counter = 1
    op = None if op_author in (None, "[deleted]") else str(op_author)

    def label(author: Any) -> str:
        nonlocal counter

        if author in (None, "[deleted]"):
            return "DELETED_USER"

        key = str(author)

        if op is not None and key == op:
            return "OP"

        if key not in mapping:
            mapping[key] = f"USER_{counter:03d}"
            counter += 1

        return mapping[key]

    return label


def tree_nodes(payload: dict[str, Any]) -> list[Any]:
    data = payload.get("data", payload)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        children = data.get("children")
        if isinstance(children, list):
            return children

    return []


def flatten(nodes: list[Any], label) -> tuple[list[dict[str, Any]], int]:
    out: list[dict[str, Any]] = []
    automod_excluded = 0

    def visit(node: Any, depth: int = 0) -> None:
        nonlocal automod_excluded

        if not isinstance(node, dict):
            return

        if node.get("kind") == "more":
            return

        data = node.get("data") if isinstance(node.get("data"), dict) else node

        if not isinstance(data, dict):
            return

        if data.get("id") is not None and data.get("body") is not None:
            author = str(data.get("author") or "")

            if author.lower() == "automoderator":
                automod_excluded += 1
            else:
                out.append(
                    {
                        "comment_id": str(data["id"]),
                        "parent_id": (
                            None
                            if data.get("parent_id") is None
                            else str(data["parent_id"])
                        ),
                        "created_utc": data.get("created_utc"),
                        "body": data.get("body"),
                        "score": data.get("score"),
                        "depth": data.get("depth", depth),
                        "author_role": label(data.get("author")),
                        "is_submitter": bool(data.get("is_submitter", False)),
                        "edited": data.get("edited"),
                        "distinguished": data.get("distinguished"),
                        "stickied": data.get("stickied"),
                    }
                )

        replies = data.get("replies")

        if isinstance(replies, dict):
            children = replies.get("data", {}).get("children", [])
            if isinstance(children, list):
                for child in children:
                    visit(child, depth + 1)
        elif isinstance(replies, list):
            for child in replies:
                visit(child, depth + 1)

        children = data.get("children")
        if isinstance(children, list):
            for child in children:
                visit(child, depth + 1)

    for node in nodes:
        visit(node)

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []

    for item in out:
        comment_id = item["comment_id"]
        if comment_id not in seen:
            seen.add(comment_id)
            deduped.append(item)

    return deduped, automod_excluded


def fetch_comments(
    session: requests.Session,
    post_id: str,
    label,
    delay: float,
) -> tuple[list[dict[str, Any]], int]:
    payload = api_get(
        session,
        "/comments/tree",
        {
            "link_id": f"t3_{post_id}",
            "limit": COMMENT_TREE_LIMIT,
        },
        delay,
    )

    return flatten(tree_nodes(payload), label)

def collect(args: argparse.Namespace) -> None:
    output = Path(args.output)

    if output.suffix.lower() != ".jsonl":
        raise SystemExit("--output must end in .jsonl")

    if args.max_posts is not None and args.max_posts <= 0:
        raise SystemExit("--max-posts must be greater than 0 when supplied")

    output.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    cursor = args.after
    total = 0

    with output.open("w", encoding="utf-8") as handle:
        while True:
            payload = api_get(
                session,
                "/posts/search",
                {
                    "subreddit": args.subreddit,
                    "after": cursor,
                    "before": args.before,
                    "sort": "asc",
                    "limit": POST_LIMIT,
                },
                args.delay,
            )

            posts = payload.get("data") or []

            if not isinstance(posts, list) or not posts:
                break

            for post in posts:
                if args.max_posts is not None and total >= args.max_posts:
                    break

                if not isinstance(post, dict) or not post.get("id"):
                    continue

                label = pseudonymizer(post.get("author"))
                comments, automod_excluded = fetch_comments(
                    session,
                    str(post["id"]),
                    label,
                    args.delay,
                )

                record = {
                    "schema_version": "1.0",
                    "retrieved_utc": utc_now(),
                    "archive_source": "Arctic Shift",
                    "post_id": str(post["id"]),
                    "subreddit": post.get("subreddit") or args.subreddit,
                    "created_utc": post.get("created_utc"),
                    "title": post.get("title"),
                    "body": post.get("selftext"),
                    "flair": post.get("link_flair_text"),
                    "score": post.get("score"),
                    "num_comments_reported": post.get("num_comments"),
                    "url": post.get("url"),
                    "author_role": label(post.get("author")),
                    "comments_collected": len(comments),
                    "automod_comments_excluded": automod_excluded,
                    "comments": comments,
                }

                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1

                print(
                    f"{total}: {post['id']} "
                    f"({len(comments)} comments, {automod_excluded} AutoModerator excluded)"
                )

            if args.max_posts is not None and total >= args.max_posts:
                break

            last_created = posts[-1].get("created_utc")

            if last_created is None:
                raise RuntimeError(
                    "Cannot paginate: last post has no created_utc"
                )

            try:
                dt = datetime.fromtimestamp(
                    float(last_created) + 0.001,
                    tz=timezone.utc,
                )
                cursor = dt.isoformat().replace("+00:00", "Z")
            except (TypeError, ValueError, OSError):
                cursor = str(last_created)

            if len(posts) < POST_LIMIT:
                break

    print(f"Done. Wrote {total} threads to {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect archived subreddit threads from Arctic Shift."
    )

    parser.add_argument("--subreddit", default="SteamSupport")
    parser.add_argument("--after", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help="Optional maximum number of posts to collect (useful for tests)",
    )

    return parser.parse_args()


if __name__ == "__main__":
    collect(parse_args())
