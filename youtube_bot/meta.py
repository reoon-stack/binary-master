"""投稿するタイトル・説明文・タグ。

方針(Shorts で伸ばすため):
- タイトルは「当てたくなる」問いかけ + 主要ハッシュタグ。答えは絶対に書かない
- 説明文の最初のハッシュタグ 3 つはタイトル上に表示されるので、一番強いものを先頭に置く
- 説明文に「前回の答え」を書いて、続けて見る理由とコメントのきっかけを作る
- タグ(視聴者には見えない)には料理名・英語・関連ワードを入れて検索とおすすめに乗せる
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Episode:
    title: str
    description: str
    tags: list[str]


TITLES = [
    "この材料で何ができる？最後まで見て当ててね",
    "{hint}何ができる？3秒で当てたら天才",
    "ドット絵で料理してみた。何の料理かわかる？",
    "最後まで見ないとわからない料理クイズ",
    "{hint}あなたは何の料理だと思う？",
    "途中でわかったら天才。何を作ってる？",
    "ドット絵キッチンへようこそ。今日の料理は？",
    "最後の一瞬でわかる料理クイズ",
]
TITLE_TAGS = " #ドット絵 #料理 #shorts"

# 説明文のハッシュタグ(先頭 3 つがタイトルの上に表示される)
HASHTAGS = ["#ドット絵", "#料理クイズ", "#ASMR", "#ピクセルアート", "#料理", "#料理動画",
            "#料理ASMR", "#pixelart", "#cooking", "#shorts"]

COMMON_TAGS = [
    "ドット絵", "ピクセルアート", "ドット絵アニメ", "ドット絵料理", "料理", "料理動画", "料理クイズ",
    "クイズ", "何の料理", "料理ASMR", "ASMR", "癒し", "レトロゲーム",
    "16bit", "pixel art", "pixelart", "pixel art animation", "cooking", "cooking asmr",
    "asmr cooking", "satisfying", "guess the dish", "japanese food", "shorts",
]

# 料理ごとの検索ワード(タグは視聴者に見えないのでネタバレにならない)
DISH_TAGS = {
    "omurice": ["オムライス", "omurice", "洋食", "ケチャップ", "卵料理", "チキンライス"],
    "curry": ["カレーライス", "カレー", "curry rice", "japanese curry", "家庭料理"],
    "oyakodon": ["親子丼", "oyakodon", "丼", "どんぶり", "和食", "卵とじ"],
    "yakisoba": ["焼きそば", "yakisoba", "ソース焼きそば", "屋台", "麺料理"],
    "napolitan": ["ナポリタン", "napolitan", "喫茶店", "スパゲッティ", "パスタ", "昭和レトロ"],
    "nikujaga": ["肉じゃが", "nikujaga", "和食", "煮物", "おふくろの味", "家庭料理"],
    "tonjiru": ["豚汁", "tonjiru", "味噌汁", "汁物", "和食", "あったかい"],
    "minestrone": ["ミネストローネ", "minestrone", "スープ", "トマトスープ", "洋食"],
}


def build_episode(dish, index: int, prev_dish=None) -> Episode:
    title = TITLES[index % len(TITLES)].format(hint=dish.hint)
    title = title[: 100 - len(TITLE_TAGS)] + TITLE_TAGS

    lines = [
        "何の料理か、わかったらコメントで教えてね！",
        "途中のどこでわかったかも書いてくれると嬉しいです。",
        "",
    ]
    if prev_dish is not None:
        lines += [f"▼ 前回の答え：{prev_dish.answer}", ""]
    lines += [
        "答え合わせは次の動画の説明欄で！",
        "ドット絵で料理を作るショート動画を毎日 18 時ごろに投稿しています。",
        "チャンネル登録で次の料理もチェックしてね。",
        "",
        "絵・音はすべてオリジナル（包丁・炒め・煮込みの ASMR）。",
        "",
        " ".join(HASHTAGS),
    ]
    description = "\n".join(lines)

    tags = list(dict.fromkeys(DISH_TAGS.get(dish.key, [dish.answer]) + COMMON_TAGS))
    # YouTube のタグは合計 500 文字まで(スペースを含むタグは引用符の分も数える)
    out, total = [], 0
    for tg in tags:
        cost = len(tg) + (2 if " " in tg else 0) + 1
        if total + cost > 480:
            break
        out.append(tg)
        total += cost
    return Episode(title=title, description=description, tags=out)
