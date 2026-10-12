#!/usr/bin/env python3
"""Make the AI assistants film: 60 seconds of motion graphics on a 120 bpm
grid, with its own music and sound, in the four cuts the platforms want.

    python scripts/promo-film.py                    # all four cuts → promo/out/film/
    python scripts/promo-film.py --cut en-16x9      # one cut
    python scripts/promo-film.py --stills 4,20.5    # frames as PNGs, to check a moment
    python scripts/promo-film.py --preview          # a quick half-size, 30 fps draft
    python scripts/promo-film.py --audio-only       # just the soundtrack (WAV)

The picture is promo/film/film.html: one page that draws any moment of the
film, built from the app's own icon, icon set, fonts and components. Each
frame is rendered on its own in Chromium (two exposures a frame, averaged,
for motion blur) by several workers at once. The music is made here, note by
note, so it lines up with the picture to the sample and needs no licence;
the sound effects come from the cue list the page keeps (FILM.cues).

    en-16x9  1920×1080  X, LinkedIn          zh-16x9  1920×1080  Bilibili
    en-9x16  1080×1920  TikTok               zh-9x16  1080×1920  Xiaohongshu

Needs Playwright, numpy and the bundled ffmpeg (pip install playwright
imageio-ffmpeg numpy pillow), not app dependencies.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import math
import multiprocessing as mp
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "promo/out/film"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 48000
BPM = 120
BEAT = 60 / BPM
DUR = 60.0
CUTS = {"en-16x9": (1920, 1080, "en"), "zh-16x9": (1920, 1080, "zh"),
        "en-9x16": (1080, 1920, "en"), "zh-9x16": (1080, 1920, "zh")}


# --------------------------------------------------------------------------- serving the page

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve() -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(_Quiet, directory=str(ROOT))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def open_page(pw, port, w, h, lang):
    browser = pw.chromium.launch(args=["--force-color-profile=srgb", "--disable-lcd-text", "--font-render-hinting=none"])
    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    for attempt in range(3):      # a busy machine can be slow to start a page
        try:
            page.goto(f"http://127.0.0.1:{port}/promo/film/film.html?w={w}&h={h}&lang={lang}", timeout=180000)
            page.wait_for_function("window.FILM && window.FILM.ready", timeout=180000)
            return browser, page
        except Exception:
            if attempt == 2:
                raise


# --------------------------------------------------------------------------- frames

def _worker(args):
    port, w, h, lang, fps, sub, f0, f1, out_path, scale = args
    from playwright.sync_api import sync_playwright
    ow, oh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    vf = []
    if sub > 1:
        vf.append(f"tmix=frames={sub}")
        vf.append(f"select='not(mod(n+1\\,{sub}))'")
        vf.append(f"setpts=N/{fps}/TB")
    if scale != 1:
        vf.append(f"scale={ow}:{oh}:flags=lanczos")
    cmd = [FFMPEG, "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps * sub), "-i", "-"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "8", "-pix_fmt", "yuv444p", out_path]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, w, h, lang)
        cdp = page.context.new_cdp_session(page)
        import base64
        for f in range(f0, f1):
            for k in range(sub):
                t = f / fps + (k / sub) * (0.5 / fps)      # a 180° shutter
                page.evaluate(f"FILM.render({t:.6f})")
                shot = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
                enc.stdin.write(base64.b64decode(shot["data"]))
        browser.close()
    enc.stdin.close()
    if enc.wait():
        raise SystemExit(f"ffmpeg failed on frames {f0}–{f1}")
    return out_path


def render_video(cut: str, port: int, tmp: Path, fps: int, sub: int, scale: float, workers: int) -> Path:
    w, h, lang = CUTS[cut]
    frames = int(round(DUR * fps))
    step = math.ceil(frames / workers)
    jobs = [(port, w, h, lang, fps, sub, a, min(frames, a + step), str(tmp / f"{cut}-{i:02d}.mp4"), scale)
            for i, a in enumerate(range(0, frames, step))]
    with mp.get_context("spawn").Pool(len(jobs)) as pool:
        parts = pool.map(_worker, jobs)
    listing = tmp / f"{cut}-parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    silent = tmp / f"{cut}-silent.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(silent)], check=True)
    return silent


def stills(times: list[float], port: int, cuts: list[str]):
    from playwright.sync_api import sync_playwright
    out = OUT / "stills"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        for cut in cuts:
            w, h, lang = CUTS[cut]
            browser, page = open_page(pw, port, w, h, lang)
            for t in times:
                page.evaluate(f"FILM.render({t})")
                path = out / f"{cut}-{t:06.2f}.png"
                page.screenshot(path=str(path))
                print(path)
            browser.close()


def get_cues(port: int, cut: str) -> list[dict]:
    from playwright.sync_api import sync_playwright
    w, h, lang = CUTS[cut]
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, w, h, lang)
        cues = page.evaluate("FILM.cues")
        browser.close()
    return cues


# --------------------------------------------------------------------------- sound: building blocks

def t_axis(seconds):
    return np.arange(int(seconds * SR)) / SR


def env_exp(n, decay, attack=0.002):
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1) if attack > 0 else 1
    return a * np.exp(-t / decay)


def lowpass(x, cutoff):
    """One-pole-ish low pass by FFT (cutoff may be a float)."""
    n = len(x)
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(X * (g[:, None] if x.ndim == 2 else g), n, axis=0)


def highpass(x, cutoff):
    n = len(x)
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = 1 / np.sqrt(1 + (cutoff / np.maximum(f, 1e-3)) ** 4)
    return np.fft.irfft(X * (g[:, None] if x.ndim == 2 else g), n, axis=0)


def bandpass(x, lo, hi):
    return highpass(lowpass(x, hi), lo)


def svf_sweep(x, f0, f1, q=0.7, mode="lp"):
    """A state-variable filter whose cutoff glides from f0 to f1 (log)."""
    n = len(x)
    fc = f0 * (f1 / f0) ** (np.arange(n) / max(1, n - 1))
    g = np.tan(np.pi * np.minimum(fc, SR * 0.45) / SR)
    k = 1 / q
    a1 = 1 / (1 + g * (g + k))
    ic1 = ic2 = 0.0
    out = np.empty(n)
    for i in range(n):
        v3 = x[i] - ic2
        v1 = a1[i] * ic1 + g[i] * a1[i] * v3
        v2 = ic2 + g[i] * v1
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        out[i] = v2 if mode == "lp" else (v1 if mode == "bp" else x[i] - k * v1 - v2)
    return out


def note_freq(name: str) -> float:
    names = {"C": -9, "C#": -8, "Db": -8, "D": -7, "D#": -6, "Eb": -6, "E": -5, "F": -4, "F#": -3, "Gb": -3,
             "G": -2, "G#": -1, "Ab": -1, "A": 0, "A#": 1, "Bb": 1, "B": 2}
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((names[pitch] + (octave - 4) * 12) / 12)


RNG = np.random.default_rng(7)


def noise(n):
    return RNG.standard_normal(n)


def place(track, sound, at, gain=1.0, pan=0.0):
    """Add a mono or stereo sound into a stereo track at a time (seconds)."""
    i = int(round(at * SR))
    if i >= len(track):
        return
    if sound.ndim == 1:
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        sound = np.stack([sound * l * 1.414, sound * r * 1.414], axis=1)
    j = min(len(track), i + len(sound))
    if i < 0:
        sound = sound[-i:]
        i = 0
    track[i:j] += sound[: j - i] * gain


# --------------------------------------------------------------------------- instruments

@functools.lru_cache(None)
def kick(big=False):
    n = int(0.55 * SR)
    t = np.arange(n) / SR
    f = 46 + 110 * np.exp(-t / 0.035) + 40 * np.exp(-t / 0.006)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / (0.26 if big else 0.18))
    knock = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.028) * 0.45
    click = bandpass(noise(n), 1500, 9000) * np.exp(-t / 0.003) * 0.5
    x = np.tanh((body * 0.8 + knock + click) * (2.2 if big else 1.8))
    return x * 0.85


@functools.lru_cache(None)
def clap():
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    e = np.zeros(n)
    for d in (0, 0.011, 0.022):
        e += np.where(t >= d, np.exp(-(t - d) / 0.006), 0)
    e += np.where(t >= 0.03, np.exp(-(t - 0.03) / 0.09), 0) * 0.7
    return bandpass(noise(n) * e, 900, 5200) * 0.6


@functools.lru_cache(None)
def hat(open_=False):
    n = int((0.25 if open_ else 0.07) * SR)
    t = np.arange(n) / SR
    x = highpass(noise(n), 7000) * np.exp(-t / (0.07 if open_ else 0.014))
    return x * (0.32 if open_ else 0.38)


@functools.lru_cache(None)
def shaker():
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    return bandpass(noise(n), 5000, 12000) * np.sin(np.pi * t / t[-1]) ** 2 * 0.18


@functools.lru_cache(None)
def snare():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.04) * 0.5
    nz = bandpass(noise(n), 1200, 9000) * np.exp(-t / 0.07)
    return (tone + nz) * 0.5


def fm(freq, dur, ratio=3.5, index=2.5, decay=0.6, idecay=0.25, attack=0.003):
    t = t_axis(dur)
    mod = np.sin(2 * np.pi * freq * ratio * t) * index * np.exp(-t / idecay)
    return np.sin(2 * np.pi * freq * t + mod) * env_exp(len(t), decay, attack)


@functools.lru_cache(None)
def bell(freq, dur=1.6):
    return fm(freq, dur, 3.5, 3.0, 0.7, 0.18) * 0.5 + fm(freq * 2, dur, 1.0, 0.8, 0.35, 0.1) * 0.15


@functools.lru_cache(None)
def pluck(freq, dur=0.5, bright=1.0):
    return fm(freq, dur, 1.0, 1.6 * bright, 0.16, 0.05) * 0.5 + fm(freq * 2.0, dur, 2.0, 0.6, 0.08, 0.04) * 0.12 * bright


def saw(freq, dur, detune=0.0, phase=0.0):
    t = t_axis(dur)
    return 2 * ((freq * (1 + detune) * t + phase) % 1.0) - 1


def supersaw(freqs, dur, voices=5, spread=0.012):
    out = np.zeros(int(dur * SR))
    for f in freqs:
        for v in range(voices):
            d = (v - (voices - 1) / 2) / ((voices - 1) / 2) * spread
            out += saw(f, dur, d, RNG.random())
    return out / (len(freqs) * voices) ** 0.5


def supersaw2(freqs, dur, voices=5, spread=0.012):
    """Two independent supersaws, one per side: real stereo width."""
    return np.stack([supersaw(freqs, dur, voices, spread * 1.1), supersaw(freqs, dur, voices, spread * 0.9)], axis=1)


def mid_bass(freq, dur, decay=0.2):
    """The bass an octave up, buzzy, so small speakers carry the line."""
    t = t_axis(dur)
    x = lowpass(saw(freq * 2, dur) + 0.5 * saw(freq * 2, dur, 0.006), 1100)
    return x * np.minimum(1, t / 0.004) * np.exp(-t / decay) * np.minimum(1, (dur - t) / 0.01)


def sub(freq, dur, decay=0.25):
    t = t_axis(dur)
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    e = np.minimum(1, t / 0.004) * np.exp(-t / decay) * np.minimum(1, (dur - t) / 0.01)
    return np.tanh(x * 1.6) * e


def reverb_ir(seconds=2.4, predelay=0.02, damp=6000):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2))
    for c in range(2):
        ir[:, c] = noise(n) * np.exp(-t / (seconds / 6.9) * 1.0)
    ir = lowpass(ir, damp)
    ir[: int(predelay * SR)] = 0
    return ir / np.sqrt((ir ** 2).sum(axis=0))


def convolve(x, ir):
    n = len(x) + len(ir) - 1
    N = 1 << (n - 1).bit_length()
    out = np.zeros((len(x), 2))
    for c in range(2):
        y = np.fft.irfft(np.fft.rfft(x[:, c], N) * np.fft.rfft(ir[:, c], N), N)[: len(x)]
        out[:, c] = y
    return out


# --------------------------------------------------------------------------- the music

CHORDS = {  # A minor: i – VI – III – VII, then C major for the logo
    "Am": ["A3", "C4", "E4", "B4"], "F": ["F3", "A3", "C4", "E4"], "C": ["C4", "E4", "G4", "D5"], "G": ["G3", "B3", "D4", "A4"],
    "Cmaj9": ["C3", "G3", "B3", "D4", "E4", "G4"],
}
ROOTS = {"Am": "A1", "F": "F1", "C": "C2", "G": "G1", "Cmaj9": "C2"}
PROG = ["Am", "F", "C", "G"]
HOOK = [(0, "E5"), (0.75, "D5"), (1.5, "C5"), (2, "A4"), (2.75, "C5"), (3.5, "D5"), (4, "E5"), (4.75, "G5"), (5.5, "E5"), (6, "D5"), (6.5, "C5"), (7, "D5")]
HOOK2 = [(0, "E5"), (0.75, "D5"), (1.5, "C5"), (2, "A4"), (2.75, "C5"), (3.5, "E5"), (4, "G5"), (4.75, "A5"), (5.5, "G5"), (6, "E5"), (6.5, "D5"), (7, "B4")]
ARP = [0, 2, 1, 3, 2, 1, 3, 2]   # chord tones for the 8th-note pluck


def chord_at(t):
    bar = int(t // (4 * BEAT))
    return PROG[bar % 4]


def music() -> tuple[np.ndarray, np.ndarray]:
    """The track, and a send for the reverb. Sections (seconds):
    0 intro · 4 kick · 8 groove · 14 full · 18 build · 20 drop · 28 groove ·
    36 breakdown · 42 build · 44 drop 2 · 52 rise · 54 the logo."""
    n = int((DUR + 0.5) * SR)
    drums, bass, keys, pad, lead, send = (np.zeros((n, 2)) for _ in range(6))
    kicks = []

    def kicks_in(a, b, step=BEAT, big=False, gain=1.0):
        t = a
        while t < b - 1e-6:
            place(drums, kick(big), t, gain)
            kicks.append(t)
            t += step

    # drums
    kicks_in(4, 19.5)
    kicks_in(20, 36, big=True)
    for bar in range(18, 21):                       # half-time breakdown: kick on 1 and the "and" of 3
        place(drums, kick(), bar * 2, 0.9); kicks.append(bar * 2)
        place(drums, kick(), bar * 2 + 1.25, 0.6); kicks.append(bar * 2 + 1.25)
    kicks_in(42, 43.5, step=BEAT)
    kicks_in(44, 52, big=True, gain=1.05)
    for a, b in ((8, 19.5), (20, 36), (44, 52)):
        t = a + BEAT
        while t < b:
            place(drums, clap(), t, 0.85, 0.05); send_ = clap() * 0.25; place(send, send_, t)
            t += 2 * BEAT
    for bar in range(18, 22):                        # breakdown clap on 3
        if bar * 2 + 1 < 42:
            place(drums, clap(), bar * 2 + 1, 0.7); place(send, clap() * 0.4, bar * 2 + 1)
    for a, b, lvl in ((0, 4, 0.35), (4, 8, 0.6), (8, 19.5, 1), (20, 36, 1), (44, 52, 1.1)):
        t = a
        i = 0
        while t < b - 1e-6:
            if a < 4:
                place(drums, hat(), t, lvl * (1 if i % 2 == 0 else 0.6), 0.3)
            else:
                place(drums, hat(open_=(i % 2 == 1)), t + (0 if i % 2 == 0 else 0.02), lvl * (0.5 if i % 2 == 0 else 0.7), 0.25 if i % 2 else -0.2)
            t += BEAT / 2
            i += 1
    for a, b in ((14, 19.5), (20, 36), (44, 52)):
        t = a
        i = 0
        while t < b - 1e-6:
            place(drums, shaker(), t + BEAT / 4, 0.8 if i % 2 else 0.5, -0.35)
            t += BEAT / 2
            i += 1
    # snare builds into each drop
    for a, b in ((18, 19.75), (42, 43.75)):
        t, k = a, 0
        while t < b - 1e-6:
            prog = (t - a) / (b - a)
            place(drums, snare(), t, 0.25 + 0.6 * prog, 0.1 * math.sin(k))
            place(send, snare() * 0.3, t)
            t += BEAT / 2 if prog < 0.5 else (BEAT / 4 if prog < 0.85 else BEAT / 8)
            k += 1
    # bass: off-beat 8ths in the grooves, held notes in the breakdown
    for a, b, lvl in ((4, 19.5, 0.8), (20, 36, 1.0), (44, 52, 1.05)):
        t = a
        while t < b - 1e-6:
            f = note_freq(ROOTS[chord_at(t)])
            place(bass, sub(f, BEAT / 2 * 0.95, 0.18), t + BEAT / 2, lvl)
            place(bass, mid_bass(f, BEAT / 2 * 0.9, 0.14), t + BEAT / 2, lvl * 0.32)
            t += BEAT
    for bar in range(18, 22):
        t = bar * 2
        place(bass, sub(note_freq(ROOTS[chord_at(t)]), 1.9, 1.2), t, 0.8)
    # plucks: an arpeggio that opens up as the track builds
    for a, b, bright, lvl in ((4, 8, 0.4, 0.35), (8, 14, 0.7, 0.45), (14, 19.5, 1.0, 0.5), (28, 36, 0.9, 0.5), (36, 42, 0.6, 0.4)):
        t, i = a, 0
        while t < b - 1e-6:
            ch = CHORDS[chord_at(t)]
            f = note_freq(ch[ARP[i % 8]]) * 2
            x = pluck(f, 0.45, bright)
            place(keys, x, t, lvl, 0.55 * math.sin(i * 0.9))
            place(send, np.stack([x, x], 1) * 0.25 * lvl, t)
            t += BEAT / 2
            i += 1
    # pad: warm chords, filtered, everywhere but the drops' supersaw
    def pad_chord(name, at, dur, lvl=0.35, cut=1800):
        x = supersaw2([note_freq(nm) for nm in CHORDS[name]], dur, voices=3, spread=0.007)
        x = lowpass(x, cut)
        e = (np.minimum(1, t_axis(dur) / 0.25) * np.minimum(1, (dur - t_axis(dur)) / 0.3))[:, None]
        place(pad, x * e, at, lvl)
        place(send, x * e * 0.3 * lvl, at)
    for bar in range(0, 10):
        pad_chord(PROG[bar % 4], bar * 2, 2.05, 0.22 if bar < 2 else 0.28, 900 + bar * 250)
    for bar in range(14, 22):
        pad_chord(PROG[bar % 4], bar * 2, 2.05, 0.3, 2400)
    pad_chord("Am", 52, 2.0, 0.35, 1400)
    # supersaw chords in the drops, pumping with the kick
    for a, b, lvl in ((20, 28, 0.42), (44, 52, 0.48)):
        for bar in range(int(a // 2), int(b // 2)):
            name = PROG[bar % 4]
            x = supersaw2([note_freq(nm) * 2 for nm in CHORDS[name][:3]] + [note_freq(CHORDS[name][0])], 2.0, voices=5, spread=0.014)
            x = lowpass(x, 5200)
            place(pad, x, bar * 2, lvl)
            place(send, x * 0.2 * lvl, bar * 2)
    # the hook on bells in the drops, sparse bells elsewhere
    def hook_at(a, notes, lvl, octave=1.0):
        for off, nm in notes:
            x = bell(note_freq(nm) * octave, 1.2)
            place(lead, x, a + off * BEAT, lvl, 0.25 * (1 if int(off * 2) % 2 else -1))
            place(send, np.stack([x, x], 1) * 0.5 * lvl, a + off * BEAT)
    for a in (20, 24):
        hook_at(a, HOOK if a == 20 else HOOK2, 0.42)
    for a in (44, 48):
        hook_at(a, HOOK if a == 44 else HOOK2, 0.4)
        hook_at(a, HOOK if a == 44 else HOOK2, 0.16, 2.0)
    for a in (14, 16):
        hook_at(a, HOOK[:6] if a == 14 else HOOK2[6:], 0.22)
    for t, nm in ((0.0, "E5"), (1.0, "C5"), (2.0, "A4"), (3.0, "B4"), (36, "E5"), (37.5, "D5"), (38, "C5"), (40, "A4"), (41.5, "B4")):
        x = bell(note_freq(nm), 2.0)
        place(lead, x, t, 0.3, -0.2)
        place(send, np.stack([x, x], 1) * 0.7 * 0.3, t)
    # the logo: a wide C major chord and a sub boom
    x = supersaw2([note_freq(nm) for nm in CHORDS["Cmaj9"]], 6.0, voices=5, spread=0.01)
    x = lowpass(x, 3200) * np.exp(-t_axis(6.0) / 2.6)[:, None]
    place(pad, x, 54.0, 0.6)
    place(send, x * 0.5, 54.0)
    hold = supersaw2([note_freq(nm) for nm in CHORDS["Cmaj9"]], 5.5, voices=3, spread=0.006)
    th = t_axis(5.5)
    hold = lowpass(hold, 1500) * (np.minimum(1, th / 1.5) * np.minimum(1, (5.5 - th) / 0.8))[:, None]
    place(pad, hold, 54.5, 0.28)
    place(send, hold * 0.25, 54.5)
    for nm in ("C4", "G4", "E5", "C6"):
        xb = bell(note_freq(nm), 4.0)
        place(lead, xb, 54.0, 0.22)
        place(send, np.stack([xb, xb], 1) * 0.3, 54.0)
    place(bass, sub(note_freq("C1"), 3.0, 1.3), 54.0, 1.2)
    place(drums, kick(True), 54.0, 1.2)

    # sidechain: the pad and bass duck under every kick
    duck = np.ones(n)
    tt = np.arange(int(0.4 * SR)) / SR
    shape = 1 - 0.75 * np.exp(-tt / 0.09) * np.minimum(1, tt / 0.004 + 0.6)
    for k in kicks:
        i = int(k * SR)
        j = min(n, i + len(shape))
        duck[i:j] = np.minimum(duck[i:j], shape[: j - i])
    pad *= duck[:, None]
    bass *= (0.35 + 0.65 * duck)[:, None]
    keys *= (0.6 + 0.4 * duck)[:, None]
    # stereo width for the pad
    d = int(0.012 * SR)
    pad[:, 1] = np.concatenate([pad[:d, 1] * 0, pad[:-d, 1]]) * 0.5 + pad[:, 1] * 0.5
    track = drums * 0.85 + bass * 0.55 + keys * 1.15 + pad * 1.2 + lead * 1.25
    return track, send


# --------------------------------------------------------------------------- sound effects

def whoosh(dur=0.6, up=True, lvl=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** (1.5 if up else 0.8)
    if not up:
        e = np.exp(-t / (dur * 0.35)) * np.minimum(1, t / 0.02)
    f0, f1 = (300, 6000) if up else (5000, 250)
    return svf_sweep(noise(n), f0, f1, 1.2, "bp") * e * lvl * 1.4


def mixp(*xs):
    """Sum sounds of different lengths."""
    out = np.zeros(max(len(x) for x in xs))
    for x in xs:
        out[: len(x)] += x
    return out


def blip(f=1200, dur=0.09, drop=0.6):
    t = t_axis(dur)
    fr = f * (1 - drop * (t / dur))
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / (dur * 0.35)) * np.minimum(1, t / 0.002)


@functools.lru_cache(None)
def sfx(name: str, f: float = 0.0):
    if name == "scribble":
        n = int(0.16 * SR)
        x = bandpass(noise(n), 2500, 9000) * (0.5 + 0.5 * np.abs(np.sin(np.arange(n) / SR * 2 * np.pi * 38)))
        return x * np.sin(np.pi * np.arange(n) / n) * 0.35
    if name == "tickclock":
        out = np.zeros(int(4 * SR))
        for i in range(8):
            x = blip(2400 if i % 2 == 0 else 1800, 0.03, 0.1) * 0.15
            out[int(i * 0.5 * SR): int(i * 0.5 * SR) + len(x)] += x
        return out
    if name == "pop":
        p = f or 1.0
        x = blip(520 * p, 0.12, 0.45) * 0.55
        c = bandpass(noise(int(0.012 * SR)), 1500, 7000) * 0.12
        x[: len(c)] += c
        return x
    if name == "flip":
        return mixp(blip(1800, 0.035, 0.3) * 0.3, highpass(noise(int(0.035 * SR)), 5000) * np.exp(-np.arange(int(0.035 * SR)) / SR / 0.006) * 0.25)
    if name == "key":
        n = int(0.03 * SR)
        return mixp(bandpass(noise(n), 1500, 7000) * np.exp(-np.arange(n) / SR / 0.004) * 0.5, blip(3000, 0.012, 0.2) * 0.1)
    if name == "click":
        return mixp(blip(1500, 0.04, 0.5) * 0.6, bandpass(noise(int(0.01 * SR)), 2000, 8000) * 0.3)
    if name == "tap":
        return blip(900, 0.05, 0.5) * 0.45
    if name == "press":
        return blip(400, 0.06, 0.3) * 0.5
    if name == "swoosh":
        return whoosh(0.35, True, 0.6)
    if name == "whoosh":
        return whoosh(0.6, True, 0.9)
    if name == "zip":
        return mixp(whoosh(0.4, True, 0.5), blip(800, 0.4, -1.2) * 0.06)
    if name == "scan":
        n = int(0.8 * SR)
        t = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(600 + 1400 * t / 0.8) / SR) * 0.07 * np.sin(np.pi * t / 0.8) + svf_sweep(noise(n), 800, 5000, 3, "bp") * 0.2 * np.sin(np.pi * t / 0.8)
    if name == "hit":
        p = f or 1.0
        n = int(0.4 * SR)
        t = np.arange(n) / SR
        return mixp(np.sin(2 * np.pi * np.cumsum(90 + 200 * np.exp(-t / 0.02)) / SR) * np.exp(-t / 0.12) * 0.6, bell(note_freq("E5") * p / 1.2, 0.4)[:n] * 0.25)
    if name == "drop":
        p = f or 1.0
        n = int(0.3 * SR)
        t = np.arange(n) / SR
        return np.sin(2 * np.pi * np.cumsum(140 * p + 120 * np.exp(-t / 0.03)) / SR) * np.exp(-t / 0.08) * 0.6 + bandpass(noise(n), 300, 2000) * np.exp(-t / 0.02) * 0.3
    if name == "impact":
        n = int(2.0 * SR)
        t = np.arange(n) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 90 * np.exp(-t / 0.05)) / SR) * np.exp(-t / 0.6)
        crack = lowpass(noise(n), 6000) * np.exp(-t / 0.18) * 0.5
        return np.tanh((boom + crack) * 1.5) * 0.8
    if name == "approve":
        n = int(2.0 * SR)
        out = sfx("impact")[:n] * 0.5
        for i, nm in enumerate(("C5", "E5", "G5", "C6")):
            b = bell(note_freq(nm), 1.6)
            k = int(i * 0.04 * SR)
            out[k:k + len(b)] += b[: n - k] * 0.45
        return out
    if name == "note":
        scale = ["A4", "C5", "D5", "E5", "G5", "A5", "C6", "D6", "E6", "G6", "A6"]
        return bell(note_freq(scale[int(f) % len(scale)]), 0.8) * 0.5
    if name == "tick":
        p = f or 1.0
        return blip(2000 * p, 0.03, 0.2) * 0.35
    if name == "shutter":
        n = int(0.18 * SR)
        x = np.zeros(n)
        for d in (0, 0.07):
            k = int(d * SR)
            c = bandpass(noise(int(0.03 * SR)), 1500, 9000) * np.exp(-np.arange(int(0.03 * SR)) / SR / 0.006)
            x[k:k + len(c)] += c
        return x * 0.7
    if name == "blip":
        return mixp(blip(1320, 0.08, 0) * 0.35, blip(1760, 0.12, 0) * 0.3)
    if name == "chime":
        out = np.zeros(int(1.6 * SR))
        for i, nm in enumerate(("E5", "B5")):
            b = bell(note_freq(nm), 1.4)
            k = int(i * 0.07 * SR)
            out[k:k + len(b)] += b[: len(out) - k] * 0.4
        return out
    if name == "crash":
        n = int(2.2 * SR)
        t = np.arange(n) / SR
        return highpass(noise(n), 4000) * np.exp(-t / 0.6) * 0.35
    if name == "shuffle":
        out = np.zeros(int(0.6 * SR))
        for i in range(10):
            x = whoosh(0.18, True, 0.25)
            k = int(i * 0.035 * SR)
            out[k:k + len(x)] += x[: len(out) - k]
        return out
    if name == "count":
        out = np.zeros(int(0.6 * SR))
        for i in range(12):
            x = blip(1400 + i * 90, 0.025, 0) * 0.2
            k = int(i * 0.038 * SR)
            out[k:k + len(x)] += x
        return out
    if name == "alert":
        return np.concatenate([blip(880, 0.1, 0) * 0.35, blip(1175, 0.2, 0) * 0.35])
    if name in ("riser", "riser2"):
        dur = 2.0
        n = int(dur * SR)
        t = np.arange(n) / SR
        x = svf_sweep(noise(n), 200, 9000, 2.5, "bp") * (t / dur) ** 2 * 1.3
        x += np.sin(2 * np.pi * np.cumsum(200 * 2 ** (3 * t / dur)) / SR) * (t / dur) ** 3 * 0.12
        x[int(1.96 * SR):] *= np.linspace(1, 0, n - int(1.96 * SR))
        return x * (1 if name == "riser" else 0.8)
    if name == "reverse":
        n = int(2.0 * SR)
        t = np.arange(n) / SR
        x = highpass(noise(n), 2500) * (t / 2.0) ** 3 * 0.6 + svf_sweep(noise(n), 300, 8000, 1.5, "bp") * (t / 2.0) ** 2 * 0.8
        x[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))
        return x
    if name == "final":
        out = sfx("impact") * 0.9
        return out
    if name == "bell":
        nm = ["E5", "G5", "C6"][int(f) % 3]
        return bell(note_freq(nm), 2.2) * 0.45
    raise KeyError(name)


def effects(cues: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    n = int((DUR + 0.5) * SR)
    dry, wet = np.zeros((n, 2)), np.zeros((n, 2))
    for c in cues:
        x = sfx(c["n"], float(c.get("f") or 0))
        place(dry, x, c["t"], c["g"], max(-1, min(1, c["p"])))
        if c["n"] in ("note", "chime", "approve", "hit", "bell", "pop", "impact", "final", "blip"):
            place(wet, x, c["t"], c["g"] * 0.35, max(-1, min(1, c["p"])))
    return dry, wet


def soundtrack(cues: list[dict], path: Path):
    track, send = music()
    dry, wet = effects(cues)
    ir = reverb_ir(2.6)
    verb = convolve(send * 0.6 + wet, ir)
    mixd = track + dry * 0.85 + verb * 0.55
    mixd = highpass(mixd, 32)
    mid, side = (mixd[:, 0] + mixd[:, 1]) / 2, (mixd[:, 0] - mixd[:, 1]) / 2
    side = highpass(side, 200) * 1.5
    mid = mid + 0.25 * bandpass(mid, 1500, 6000)
    mixd = np.stack([mid + side, mid - side], axis=1)
    # glue: gentle compression via a soft knee, then a limiter-ish soft clip
    peak = np.abs(mixd).max()
    mixd = mixd / peak * 1.25
    mixd = np.tanh(mixd * 1.1) / np.tanh(1.1 * 1.25) * 0.95
    mixd = mixd[: int(DUR * SR)]
    fade = int(0.04 * SR)
    mixd[-fade:] *= np.linspace(1, 0, fade)[:, None]
    pcm = (np.clip(mixd, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


# --------------------------------------------------------------------------- putting it together

def finish(silent: Path, audio: Path, out: Path, preview: bool):
    grain = [] if preview else ["-vf", "noise=alls=3:allf=t,format=yuv420p"]
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(silent), "-i", str(audio),
                    *grain, "-c:v", "libx264", "-preset", "fast" if preview else "slow", "-crf", "24" if preview else "16",
                    "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k",
                    "-movflags", "+faststart", "-shortest", str(out)], check=True)


def cover(port: int, cut: str, t: float, out: Path):
    from playwright.sync_api import sync_playwright
    w, h, lang = CUTS[cut]
    with sync_playwright() as pw:
        browser, page = open_page(pw, port, w, h, lang)
        page.evaluate(f"FILM.render({t})")
        page.screenshot(path=str(out))
        browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cut", action="append", choices=list(CUTS), help="which cut (repeatable; default all four)")
    ap.add_argument("--stills", help="comma-separated times: write PNGs instead of a video")
    ap.add_argument("--preview", action="store_true", help="half size, 30 fps, no motion blur")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    cuts = args.cut or list(CUTS)
    OUT.mkdir(parents=True, exist_ok=True)
    httpd, port = serve()
    try:
        if args.stills:
            stills([float(x) for x in args.stills.split(",")], port, cuts)
            return
        cues = get_cues(port, cuts[0])
        audio = soundtrack(cues, OUT / "soundtrack.wav")
        print("soundtrack:", audio)
        if args.audio_only:
            return
        tmp = Path(tempfile.mkdtemp(prefix="biomanager-film-"))
        try:
            for cut in cuts:
                fps, sub, scale = (30, 1, 0.5) if args.preview else (60, 2, 1.0)
                silent = render_video(cut, port, tmp, fps, sub, scale, args.workers)
                name = f"biomanager-ai-{cut}{'-preview' if args.preview else ''}.mp4"
                finish(silent, audio, OUT / name, args.preview)
                if not args.preview:
                    cover(port, cut, 58.5, OUT / f"biomanager-ai-{cut}-cover.png")
                print(OUT / name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
