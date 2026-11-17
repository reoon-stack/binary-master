"""今日投稿する「究極の2択」動画の台本を作る。

1本に3問。各問は
  めたんが出題 → 3秒カウントダウン → ずんだもんとめたんが別々の側を選んで理由を言う
最後に「コメントで 1A 2B 3A みたいに教えてね」と呼びかける。
2択のネタは choices.json。日付で順番に使う(状態ファイル不要)。
"""

from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

CHOICES_PATH = Path(__file__).with_name("choices.json")
QUESTIONS_PER_VIDEO = 3
KANJI_NUMS = ["1", "2", "3"]

SPEAKERS = {
    "m": {"name": "四国めたん", "voicevox_id": 2, "color": (190, 110, 230)},
    "z": {"name": "ずんだもん", "voicevox_id": 3, "color": (110, 200, 80)},
}

COMMON_TAGS = ["究極の2択", "2択", "どっち派", "心理テスト", "ずんだもん", "四国めたん",
               "VOICEVOX", "shorts"]


@dataclass
class Choice:
    text: str
    emoji: str
    reason: str


@dataclass
class Question:
    a: Choice
    b: Choice


@dataclass
class Step:
    kind: str                  # "line" | "countdown"
    q: int                     # 何問目か (0始まり)
    speaker: str = ""
    text: str = ""
    pick: str | None = None    # この発言で選んだ側 "a" / "b"


@dataclass
class Episode:
    title: str
    description: str
    tags: list[str]
    questions: list[Question]
    steps: list[Step] = field(default_factory=list)


def day_number(date: dt.date) -> int:
    return (date - dt.date(2026, 1, 1)).days


def load_choices() -> list[Question]:
    raw = json.loads(CHOICES_PATH.read_text(encoding="utf-8"))
    return [Question(Choice(*r[:3]), Choice(*r[3:])) for r in raw]


def make_episode(index: int) -> Episode:
    bank = load_choices()
    # 1本3問。ネタ数が3の倍数でなければ、2周目以降は組み合わせが変わる
    qs = [bank[(index * QUESTIONS_PER_VIDEO + k) % len(bank)]
          for k in range(QUESTIONS_PER_VIDEO)]
    rng = random.Random(index)

    steps: list[Step] = [Step("line", 0, "z", "究極の2択、いくのだ！")]
    for i, q in enumerate(qs):
        steps.append(Step("line", i, "m",
                          f"第{KANJI_NUMS[i]}問。{q.a.text}？それとも、{q.b.text}？"))
        steps.append(Step("countdown", i))
        z_side = rng.choice("ab")
        m_side = "b" if z_side == "a" else "a"
        zc, mc = getattr(q, z_side), getattr(q, m_side)
        steps.append(Step("line", i, "z", f"ボクは{zc.text}派なのだ！{zc.reason}からなのだ", z_side))
        steps.append(Step("line", i, "m", f"わたくしは{mc.text}派ね。{mc.reason}からよ", m_side))
    steps.append(Step("line", QUESTIONS_PER_VIDEO - 1, "m",
                      "あなたはどっち？コメントで「1A」みたいに教えてね！"))

    q0 = qs[0]
    title = f"【究極の2択】{q0.a.text} vs {q0.b.text} あなたはどっち？"
    lines = "\n".join(f"Q{i + 1}. A: {q.a.text} / B: {q.b.text}" for i, q in enumerate(qs))
    description = (
        f"究極の2択、あなたはどっちを選ぶ？\n\n{lines}\n\n"
        "コメントで「1A 2B 3A」のように答えを教えてね！\n"
        "毎日新しい2択を投稿しています。\n\n"
        "音声: VOICEVOX:四国めたん / VOICEVOX:ずんだもん\n\n"
        "#究極の2択 #どっち派 #ずんだもん #shorts"
    )
    suffix = " #shorts"
    return Episode(
        title=title[: 100 - len(suffix)] + suffix,
        description=description,
        tags=COMMON_TAGS,
        questions=qs,
        steps=steps,
    )


def episode_for(date: dt.date, index: int | None = None) -> Episode:
    return make_episode(index if index is not None else day_number(date))
