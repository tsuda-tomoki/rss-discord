#!/usr/bin/env python3
"""Post newly discovered RSS/Atom entries to a Discord webhook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

ATOM_NS = "{http://www.w3.org/2005/Atom}"
MAX_ITEMS_PER_FEED = 5
MAX_SEEN_PER_FEED = 200


def text(element: ET.Element | None, *names: str) -> str:
    if element is None:
        return ""
    for name in names:
        child = element.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def entry_link(entry: ET.Element, atom: bool) -> str:
    if not atom:
        return text(entry, "link")
    for link in entry.findall(f"{ATOM_NS}link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href", "")
    return ""


def parse_feed(payload: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is not None:
        entries: Iterable[ET.Element] = channel.findall("item")
        atom = False
    else:
        entries = root.findall(f"{ATOM_NS}entry")
        atom = True

    items = []
    for entry in entries:
        title = text(entry, f"{ATOM_NS}title" if atom else "title") or "(タイトルなし)"
        link = entry_link(entry, atom)
        identifier = text(entry, f"{ATOM_NS}id" if atom else "guid") or link or title
        item_id = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        items.append({"id": item_id, "title": title, "url": link})
    return items


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; rss-discord/1.0; "
                "+https://github.com/tsuda-tomoki/rss-discord)"
            ),
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def post_to_discord(webhook_url: str, feed_name: str, item: dict[str, str]) -> None:
    content = f"**{feed_name}** に新着記事が投稿されました\n{item['title']}"
    if item["url"]:
        content += f"\n{item['url']}"
    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def load_state(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    contents = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(contents, dict):
        raise ValueError("状態ファイルは JSON オブジェクトである必要があります")
    return {str(key): list(value) for key, value in contents.items() if isinstance(value, list)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feeds", type=Path, default=Path("feeds.csv"))
    parser.add_argument("--state", type=Path, default=Path("data/seen_items.json"))
    parser.add_argument("--initialize", action="store_true", help="既存記事を通知せず、通知済みとして記録します")
    parser.add_argument("--send-latest", action="store_true", help="各フィードの最新記事をテスト送信します")
    args = parser.parse_args()

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL が設定されていません", file=sys.stderr)
        return 2

    state = load_state(args.state)
    changed = False
    errors = []
    with args.feeds.open(encoding="utf-8-sig", newline="") as csv_file:
        rows = (line for line in csv_file if not line.lstrip().startswith("#"))
        for row in csv.DictReader(rows):
            url = (row.get("url") or "").strip()
            name = (row.get("name") or url).strip()
            if not url:
                continue
            try:
                items = parse_feed(fetch(url))
                if args.send_latest:
                    if not items:
                        raise RuntimeError("記事が見つかりません")
                    post_to_discord(webhook_url, f"{name}（テスト）", items[0])
                    print(f"{name}: 最新記事をテスト送信しました")
                    continue
                known = state.get(url, [])
                known_set = set(known)
                unseen = [item for item in items if item["id"] not in known_set]
                if known and not args.initialize:
                    for item in reversed(unseen[:MAX_ITEMS_PER_FEED]):
                        post_to_discord(webhook_url, name, item)
                        time.sleep(1)
                state[url] = ([item["id"] for item in items] + known)[:MAX_SEEN_PER_FEED]
                changed = True
                print(f"{name}: {len(unseen)} 件の未通知記事")
            except (ET.ParseError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as error:
                errors.append(f"{name} ({url}): {error}")

    if changed:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
