"""投稿するタイトル・説明文・タグ。答え(料理名)はネタバレになるのでタイトルと説明文には書かない。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Episode:
    title: str
    description: str
    tags: list[str]


TITLES = [
    "【ドット絵料理】何ができるかわかる？",
    "この材料で何を作る？最後まで見て当ててね【ドット絵】",
    "{hint}何ができる？【ドット絵クッキング】",
    "3秒で当てたら天才。何の料理？【ドット絵ASMR】",
    "ドット絵で料理してみた。何ができるでしょう？",
]

COMMON_TAGS = ["ドット絵", "ピクセルアート", "pixelart", "料理", "料理ASMR", "ASMR", "クイズ",
               "何の料理", "ドット絵アニメ", "shorts"]


def build_episode(dish, index: int) -> Episode:
    title = TITLES[index % len(TITLES)].format(hint=dish.hint)
    suffix = " #shorts"
    description = (
        "ドット絵で料理を作ります。\n"
        "何の料理かわかったら、コメントで教えてね！\n\n"
        "毎日いろいろな料理を投稿しています。\n\n"
        "#ドット絵 #ピクセルアート #料理 #クイズ #shorts"
    )
    # 料理名は検索用にタグにだけ入れる(画面やタイトルには出さない)
    tags = list(dict.fromkeys(COMMON_TAGS + [dish.answer]))
    return Episode(title=title[: 100 - len(suffix)] + suffix, description=description, tags=tags)
