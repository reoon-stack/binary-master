"""音声まわり: VOICEVOX で読み上げ、BGM と効果音を合成してミックスする。

BGM と効果音はコードで合成するので、著作権の心配がない。
"""

from __future__ import annotations

import io
import json
import os
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass

import numpy as np

SR = 24000  # VOICEVOX の出力と合わせる
VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")


# ---------------------------------------------------------------- 読み上げ

def voicevox_available() -> bool:
    try:
        with urllib.request.urlopen(f"{VOICEVOX_URL}/version", timeout=3):
            return True
    except OSError:
        return False


def _post(path: str, params: dict, body: bytes | None = None) -> bytes:
    url = f"{VOICEVOX_URL}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=body or b"", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def synthesize(text: str, speaker_id: int, speed: float = 1.15) -> np.ndarray:
    query = json.loads(_post("/audio_query", {"text": text, "speaker": speaker_id}))
    query.update(speedScale=speed, prePhonemeLength=0.05, postPhonemeLength=0.1,
                 outputSamplingRate=SR, outputStereo=False)
    wav = _post("/synthesis", {"speaker": speaker_id}, json.dumps(query).encode())
    with wave.open(io.BytesIO(wav)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def placeholder_voice(text: str) -> np.ndarray:
    """VOICEVOX が無い環境(手元テスト用)。文字数から長さを見積もった無音。"""
    return np.zeros(int(SR * (0.4 + 0.13 * len(text))), dtype=np.float32)


# ---------------------------------------------------------------- BGM

def _note(freq: float, dur: float, kind: str = "pluck") -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    if kind == "pluck":
        wave_ = 0.6 * np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
        env = np.exp(-t * 6)
    else:  # pad
        wave_ = sum(np.sin(2 * np.pi * freq * m * t) / m for m in (1, 2, 3))
        env = np.minimum(1, t * 4) * np.minimum(1, (dur - t) * 4)
    env[: int(SR * 0.005)] *= np.linspace(0, 1, int(SR * 0.005))
    return (wave_ * env).astype(np.float32)


def _drum(kind: str) -> np.ndarray:
    if kind == "kick":
        t = np.arange(int(SR * 0.25)) / SR
        f = 120 * np.exp(-t * 20) + 45
        return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 12)).astype(np.float32)
    t = np.arange(int(SR * 0.06)) / SR
    rng = np.random.default_rng(7)
    return (rng.uniform(-1, 1, t.size) * np.exp(-t * 70) * 0.35).astype(np.float32)


def make_bgm(seconds: float, seed: int = 0) -> np.ndarray:
    """明るめのポップなループBGM(テンポ 112、I–V–vi–IV 系)。"""
    rng = np.random.default_rng(seed)
    bpm = 112
    beat = 60 / bpm
    root = 261.63 * 2 ** (rng.integers(-2, 3) / 12)  # 回ごとに少しキーを変える
    semis = lambda s: root * 2 ** (s / 12)
    progs = [[0, 7, 9, 5], [0, 9, 5, 7], [5, 7, 0, 9]]
    prog = progs[seed % len(progs)]
    chords = {0: [0, 4, 7], 7: [7, 11, 14], 9: [9, 12, 16], 5: [5, 9, 12]}

    out = np.zeros(int(SR * (seconds + 2)), dtype=np.float32)

    def add(sig, start, gain):
        i = int(start * SR)
        j = min(out.size, i + sig.size)
        if i < out.size:
            out[i:j] += sig[: j - i] * gain

    t, bar = 0.0, 0
    arp_pattern = [0, 1, 2, 1, 0, 2, 1, 2]
    while t < seconds + 1:
        ch = chords[prog[bar % 4]]
        add(_note(semis(ch[0] - 12), beat * 4, "pad"), t, 0.10)
        add(_note(semis(ch[1] - 12), beat * 4, "pad"), t, 0.07)
        for k, idx in enumerate(arp_pattern):
            add(_note(semis(ch[idx] + 12), beat * 0.6), t + k * beat / 2, 0.10)
        for k in range(4):
            add(_drum("kick"), t + k * beat, 0.35)
            add(_drum("hat"), t + k * beat + beat / 2, 0.5)
        t += beat * 4
        bar += 1
    out = out[: int(SR * seconds)]
    fade = int(SR * 1.0)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out / (np.abs(out).max() + 1e-9)


def pop_sfx() -> np.ndarray:
    t = np.arange(int(SR * 0.12)) / SR
    f = 500 + 900 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)).astype(np.float32)


# ---------------------------------------------------------------- ミックス

@dataclass
class Segment:
    start: float
    end: float


def mix(voices: list[np.ndarray], gap: float, tail: float, seed: int
        ) -> tuple[np.ndarray, list[Segment], float]:
    segments, t = [], 0.3
    for v in voices:
        d = v.size / SR
        segments.append(Segment(t, t + d))
        t += d + gap
    total = t - gap + tail

    n = int(SR * total)
    voice_track = np.zeros(n, dtype=np.float32)
    sfx_track = np.zeros(n, dtype=np.float32)
    pop = pop_sfx()
    for v, seg in zip(voices, segments):
        i = int(seg.start * SR)
        voice_track[i : i + v.size] += v[: n - i]
        j = max(0, i - int(SR * 0.05))
        sfx_track[j : j + pop.size] += pop[: n - j]

    bgm = make_bgm(total, seed)
    # 声がある間は BGM を下げる(ダッキング)
    hop = int(SR * 0.05)
    blocks = np.abs(voice_track[: n // hop * hop]).reshape(-1, hop).max(axis=1) > 0.01
    talking = np.convolve(blocks.astype(np.float32), np.ones(5) / 5, mode="same")
    env = np.interp(np.arange(n), np.arange(talking.size) * hop + hop / 2, talking)
    bgm_gain = 0.22 - 0.12 * np.clip(env * 2, 0, 1)
    out = voice_track * 0.95 + sfx_track * 0.18 + bgm * bgm_gain
    out /= max(1.0, float(np.abs(out).max()) / 0.95)
    return out, segments, total


def write_wav(path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
