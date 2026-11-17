"""料理のレシピ(動画の台本)。1品 = 1本の動画。

steps(調理工程)に使える動作:
  ("stir", 秒)                         木べら/お玉で混ぜる
  ("add", 種類, 秒[, 溶けた後の汁の色])  ボウルから加える(ご飯・麺・豆腐・ルウなど)
  ("liquid", 色, 量0-1, 秒)            計量カップで水やだしを注ぐ
  ("sauce", ボトル色, 具の色, 汁の色, 秒) ボトルでソースをかける。次の工程で混ざる
  ("simmer", 秒)                       ぐつぐつ煮る
  ("egg_pour", 秒)                     溶き卵を回し入れる
  ("shape", 秒)                        木べらで形を整える
  ("egg_sheet", 秒)                    もう1つのフライパンで薄焼き卵を作る

serve: (器, 盛り方, 器に先に入れておくご飯)  盛り方 = mound / pour / top_rice
garnish: 仕上げ  ("line", ボトル色, 線の色) / ("sprinkle", [色], 半径, 個数) / ("place", 種類, (dx, dy))
"""

from __future__ import annotations

from dataclasses import dataclass, field

KETCHUP = (204, 40, 36)
SAUCE = (70, 40, 24)
SOY = (40, 24, 16)
WATER = (196, 214, 214)
DASHI = (206, 166, 104)
TOMATO_BROTH = (214, 92, 60)


@dataclass
class Dish:
    key: str
    answer: str
    chop: tuple[str, str]
    extra: tuple[str, str]          # ("extra"|"ing", 名前) 冒頭で一部だけ見せる材料
    vessel: str                     # pan / pot
    steps: list
    serve: tuple
    garnish: list = field(default_factory=list)
    hint: str = ""


DISHES = [
    Dish("omurice", "オムライス", ("onion", "chicken"), ("extra", "egg"), "pan",
         [("stir", 1.8), ("add", "rice", 0.9), ("stir", 0.75),
          ("sauce", KETCHUP, (214, 92, 58), None, 0.8), ("stir", 0.8), ("shape", 0.5),
          ("egg_sheet", 2.9)],
         ("plate", "mound", None),
         [("line", KETCHUP, (196, 30, 30)), ("place", "parsley", (40, 22))],
         "卵と玉ねぎと鶏肉…"),
    Dish("curry", "カレーライス", ("potato", "pork"), ("extra", "roux"), "pot",
         [("stir", 1.4), ("add", "carrot", 0.8), ("liquid", WATER, 0.85, 1.0), ("simmer", 1.3),
          ("add", "roux", 0.8, (150, 92, 40)), ("stir", 1.2), ("simmer", 1.6)],
         ("plate", "pour", "left"),
         [("place", "fukujin", (-30, 30))],
         "じゃがいもと豚肉…"),
    Dish("oyakodon", "親子丼", ("onion", "chicken"), ("extra", "egg"), "pan",
         [("stir", 1.2), ("liquid", DASHI, 0.6, 0.9), ("simmer", 2.0), ("egg_pour", 1.3),
          ("simmer", 1.8)],
         ("donburi", "top_rice", "center"),
         [("place", "mitsuba", (6, -6))],
         "玉ねぎと鶏肉と卵…"),
    Dish("yakisoba", "焼きそば", ("cabbage", "pork"), ("extra", "noodles"), "pan",
         [("stir", 1.6), ("add", "noodles", 0.9), ("stir", 1.0),
          ("sauce", SAUCE, (184, 124, 70), None, 0.8), ("stir", 1.4), ("shape", 0.5)],
         ("plate", "mound", None),
         [("sprinkle", [(60, 130, 60), (90, 160, 70)], 34, 40), ("place", "beni", (16, -14))],
         "キャベツと豚肉…"),
    Dish("napolitan", "ナポリタン", ("green_pepper", "sausage"), ("extra", "spaghetti"), "pan",
         [("stir", 1.5), ("add", "spaghetti", 0.9), ("stir", 0.9),
          ("sauce", KETCHUP, (214, 96, 60), None, 0.8), ("stir", 1.4), ("shape", 0.5)],
         ("plate", "mound", None),
         [("sprinkle", [(250, 244, 220), (240, 226, 180)], 32, 40), ("place", "parsley", (30, -16))],
         "ピーマンとウインナー…"),
    Dish("nikujaga", "肉じゃが", ("potato", "beef"), ("ing", "carrot"), "pot",
         [("stir", 1.4), ("add", "carrot", 0.8), ("liquid", DASHI, 0.75, 1.0),
          ("sauce", SOY, None, (150, 92, 46), 0.8), ("simmer", 1.4), ("simmer", 1.4)],
         ("kobachi", "pour", None),
         [("place", "snowpea", (14, -12)), ("place", "snowpea", (-16, 10))],
         "じゃがいもと牛肉…"),
    Dish("tonjiru", "豚汁", ("daikon", "pork"), ("extra", "miso"), "pot",
         [("stir", 1.2), ("add", "carrot", 0.7), ("liquid", WATER, 0.9, 0.9), ("simmer", 1.3),
          ("add", "tofu", 0.7), ("add", "miso", 0.7, (204, 164, 104)), ("stir", 1.0),
          ("simmer", 1.2)],
         ("owan", "pour", None),
         [("sprinkle", [(90, 170, 70), (150, 210, 110)], 26, 30)],
         "大根と豚肉…"),
    Dish("minestrone", "ミネストローネ", ("tomato", "carrot"), ("ing", "onion"), "pot",
         [("stir", 1.4), ("liquid", TOMATO_BROTH, 0.85, 1.0), ("add", "beans", 0.8),
          ("simmer", 1.6), ("stir", 1.0), ("simmer", 1.6)],
         ("soup_plate", "pour", None),
         [("sprinkle", [(250, 244, 220)], 30, 30), ("place", "parsley", (8, -6))],
         "トマトとにんじん…"),
]

BY_KEY = {d.key: d for d in DISHES}
