"""今日投稿する動画の台本を決める。

ずんだもん × 四国めたん の掛け合いで「意外な雑学」を紹介する形式。
台本は scripts.json にあり、日付で順番に使う(状態ファイル不要)。
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS_PATH = Path(__file__).with_name("scripts.json")

SPEAKERS = {
    "m": {"name": "四国めたん", "voicevox_id": 2, "color": (190, 110, 230)},
    "z": {"name": "ずんだもん", "voicevox_id": 3, "color": (110, 200, 80)},
}

OUTRO = [
    ("m", "毎日ひとつ、意外な雑学を紹介しているわ", "📅"),
    ("z", "チャンネル登録して、また見に来てほしいのだ！", "🔔"),
]

COMMON_TAGS = ["雑学", "豆知識", "ずんだもん", "四国めたん", "VOICEVOX", "shorts"]


@dataclass
class Line:
    speaker: str
    text: str
    emoji: str


@dataclass
class Episode:
    title: str
    topic: str
    description: str
    tags: list[str]
    lines: list[Line] = field(default_factory=list)


def day_number(date: dt.date) -> int:
    return (date - dt.date(2026, 1, 1)).days


def load_scripts() -> list[dict]:
    return json.loads(SCRIPTS_PATH.read_text(encoding="utf-8"))


def make_episode(index: int) -> Episode:
    scripts = load_scripts()
    s = scripts[index % len(scripts)]
    lines = [Line(*l) for l in s["lines"]] + [Line(*l) for l in OUTRO]
    title = f"【雑学】{s['hook']}"
    script_text = "\n".join(
        f"{SPEAKERS[l.speaker]['name']}「{l.text}」" for l in lines[: len(s["lines"])]
    )
    description = (
        f"{s['title']}\n\n{script_text}\n\n"
        "毎日ひとつ、思わず人に話したくなる雑学をお届けします。\n\n"
        "音声: VOICEVOX:四国めたん / VOICEVOX:ずんだもん\n\n"
        "#雑学 #豆知識 #ずんだもん #shorts"
    )
    suffix = " #shorts"
    return Episode(
        title=title[: 100 - len(suffix)] + suffix,
        topic=s["hook"],
        description=description,
        tags=list(dict.fromkeys(s.get("tags", []) + COMMON_TAGS)),
        lines=lines,
    )


def episode_for(date: dt.date, index: int | None = None) -> Episode:
    return make_episode(index if index is not None else day_number(date))
