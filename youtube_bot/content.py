"""今日投稿する動画の中身(スライド・タイトル・説明文)を決める。

状態ファイルを持たずに毎日違う内容になるよう、日付から内容を決定する。
- 偶数日: 豆知識 (tips.json を順番に)
- 奇数日: 基数変換クイズ (日付をシードに乱数で出題)
"""

from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

TIPS_PATH = Path(__file__).with_name("tips.json")

APP_HINT = "基数変換マスターで\n自分でも試してみよう"
CTA = "毎日ためになる\nショート動画を投稿中\nチャンネル登録してね"


@dataclass
class Slide:
    text: str
    seconds: float = 4.0
    kind: str = "body"  # "hook" | "body" | "answer" | "cta"


@dataclass
class Episode:
    kind: str
    title: str
    description: str
    tags: list[str]
    slides: list[Slide] = field(default_factory=list)
    header: str = ""


def day_number(date: dt.date) -> int:
    return (date - dt.date(2026, 1, 1)).days


def load_tips() -> list[dict]:
    return json.loads(TIPS_PATH.read_text(encoding="utf-8"))


COMMON_TAGS = ["プログラミング", "情報", "豆知識", "勉強", "shorts"]


def _shorts_title(title: str) -> str:
    suffix = " #shorts"
    # YouTube のタイトル上限は100文字
    return title[: 100 - len(suffix)] + suffix


def make_tip(index: int) -> Episode:
    tips = load_tips()
    tip = tips[index % len(tips)]
    slides = [Slide(tip["slides"][0], 3.5, "hook")]
    slides += [Slide(t, 4.5) for t in tip["slides"][1:]]
    slides.append(Slide(CTA, 3.0, "cta"))
    body = "\n".join(s.replace("\n", "") for s in tip["slides"])
    description = (
        f"{tip['title']}\n\n{body}\n\n"
        "毎日ひとつ、コンピュータと数のためになる豆知識をお届けします。\n"
        "#豆知識 #プログラミング #shorts"
    )
    return Episode(
        kind="tip",
        title=_shorts_title(tip["title"]),
        description=description,
        tags=list(dict.fromkeys(tip.get("tags", []) + COMMON_TAGS)),
        slides=slides,
        header="今日の豆知識",
    )


BASES = {2: "2進数", 8: "8進数", 16: "16進数"}


def to_base(n: int, base: int) -> str:
    digits = "0123456789ABCDEF"
    if n == 0:
        return "0"
    out = ""
    while n:
        out = digits[n % base] + out
        n //= base
    return out


def division_steps(n: int, base: int) -> list[str]:
    digits = "0123456789ABCDEF"
    steps = []
    while n > 0:
        q, r = divmod(n, base)
        steps.append(f"{n} ÷ {base} = {q} 余り {digits[r]}")
        n = q
    return steps


def make_quiz(seed: int) -> Episode:
    rng = random.Random(seed)
    base = rng.choice([2, 2, 8, 16])  # 2進数を多めに
    n = rng.randint(10, 63) if base == 2 else rng.randint(20, 255)
    answer = to_base(n, base)
    name = BASES[base]

    steps = division_steps(n, base)
    slides = [
        Slide(f"10進数の {n} を\n{name}にすると？", 4.0, "hook"),
        Slide("考えてみよう…\n3", 1.0),
        Slide("考えてみよう…\n2", 1.0),
        Slide("考えてみよう…\n1", 1.0),
        Slide(f"正解は\n{answer}", 4.0, "answer"),
        Slide(f"解き方：\n{base}で割り続けて\n余りをメモする", 4.0),
        # 割り算の過程は1枚に最大5行まで
        *[
            Slide("\n".join(steps[i : i + 5]), 5.0)
            for i in range(0, len(steps), 5)
        ],
        Slide(f"余りを下から読むと\n{answer}", 4.0, "answer"),
        Slide(APP_HINT, 3.0, "cta"),
    ]
    description = (
        f"10進数の {n} を{name}にすると？\n\n"
        f"正解: {answer}\n\n"
        f"解き方: {base}で割り続けて、余りを下から読みます。\n"
        + "\n".join(steps)
        + "\n\n#基数変換 #2進数 #16進数 #クイズ #shorts"
    )
    return Episode(
        kind="quiz",
        title=_shorts_title(f"【基数変換クイズ】{n}を{name}にすると？"),
        description=description,
        tags=list(dict.fromkeys(["基数変換", "クイズ", name] + COMMON_TAGS)),
        slides=slides,
        header="基数変換クイズ",
    )


def episode_for(date: dt.date, kind: str | None = None, index: int | None = None) -> Episode:
    day = day_number(date)
    kind = kind or ("tip" if day % 2 == 0 else "quiz")
    if kind == "tip":
        return make_tip(index if index is not None else day // 2)
    if kind == "quiz":
        return make_quiz(index if index is not None else day)
    raise ValueError(f"unknown kind: {kind}")
