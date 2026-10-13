#!/usr/bin/env python3
"""Read lines aloud in one of BioManager's own voices, with Qwen3-TTS or VoxCPM2.

    <tts python> scripts/qwen-voice.py jobs.json

jobs.json is a list of {"voice": "zh-a", "text": "…", "out": "/path/line.wav"}.
The voices are promo/voices/<name>.wav, a short clip made once from the
description in promo/voices/voices.json; every line is read by copying that
clip, so the narrator is the same in every video. Lines whose file already
exists are skipped.

A voice's "model" in voices.json says what copies it:
    qwen     (the default) Qwen3-TTS Base: zh-a, en-b, the Mandarin and English narrators
    voxcpm2  VoxCPM2, for the dialect narrators (yue-a, sichuan-a, …): their clip is
             in the dialect and its words in "text", so the copy keeps the accent
             (scripts/dialect-voices.py makes them; Qwen3-TTS lost it in a listening test)

It runs in its own environment, not the app's: MLX on Apple silicon.
    python3.12 -m venv ~/.cache/biomanager-tts/venv
    ~/.cache/biomanager-tts/venv/bin/pip install mlx-audio soundfile
scripts/explainer-video.py and daily-video.py call it (BIOMANAGER_TTS_PYTHON
names another interpreter). Qwen3-TTS and VoxCPM2 are Apache 2.0; each model
is downloaded from Hugging Face the first time it is used (2.7 GB and 3.2 GB).
VoxCPM2 takes a few times longer than the line it reads.
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
MODELS = {"qwen": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-6bit",
          "voxcpm2": "mlx-community/VoxCPM2-8bit"}


def read(model, kind: str, voice: dict, clip: Path, text: str) -> np.ndarray:
    """One line in a voice: `voice` is its voices.json entry, `clip` its recording."""
    if kind == "voxcpm2":
        # The clip both as the voice to copy and as the start the line continues from,
        # which keeps its accent as well as its sound.
        parts = model.generate(text=text, ref_audio=str(clip), prompt_audio=str(clip), prompt_text=voice["text"])
    else:
        parts = model.generate(text=text, ref_audio=str(clip), ref_text=voice["text"], lang_code=voice["language"])
    return np.concatenate([np.array(p.audio, dtype=np.float32).reshape(-1) for p in parts])


def main():
    from mlx_audio.tts.utils import load_model

    jobs = [j for j in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if not Path(j["out"]).exists()]
    if not jobs:
        return
    voices = json.loads((ROOT / "promo/voices/voices.json").read_text(encoding="utf-8"))
    done = 0
    for kind, name in MODELS.items():
        mine = [j for j in jobs if voices[j["voice"]].get("model", "qwen") == kind]
        if not mine:
            continue
        t = time.time()
        model = load_model(name)
        print(f"qwen-voice: {kind} ready in {time.time() - t:.0f} s; {len(mine)} lines", flush=True)
        for job in mine:
            audio = read(model, kind, voices[job["voice"]], ROOT / "promo/voices" / f"{job['voice']}.wav", job["text"])
            out = Path(job["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            sf.write(f"{out}.part.wav", audio, model.sample_rate)
            os.replace(f"{out}.part.wav", out)
            done += 1
            print(f"qwen-voice: {done}/{len(jobs)}", flush=True)
        del model
        gc.collect()


if __name__ == "__main__":
    main()
