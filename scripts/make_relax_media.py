"""Generate the Relax media locally (dev-time only; nothing is downloaded).

    python scripts/make_relax_media.py          # writes media/scenes/*.png and media/audio/*.wav

Only numpy + the standard library (zlib/struct for PNG, wave for WAV): no new dependencies,
no licensing questions. Output matches what server/features/relax/router.py looks for:

    media/scenes/<scene-id>.png             earthrise, ocean-shore, forest-stream
    media/audio/<scene-id>-nature.wav       ocean-shore (waves), rain-window (rain), forest-stream (wind)
    media/audio/music-<name>.wav            one slow ambient pad, offered by every scene with "music"

Audio is mono 16-bit 22.05 kHz, 75 s, and loops seamlessly: noise is shaped in the frequency
domain (circular), every modulation and note frequency fits a whole number of cycles in the loop,
and rain drops wrap around the end. Deterministic (fixed seed).
"""
from __future__ import annotations

import struct
import wave
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / "media" / "scenes"
AUDIO = ROOT / "media" / "audio"

W, H = 1280, 720
SR = 22050
LOOP_S = 75
N = SR * LOOP_S
rng = np.random.default_rng(142)


# =========================================================================== images ==
def write_png(path: Path, rgb: np.ndarray) -> None:
    """RGB float array (H, W, 3) in 0..1 -> 8-bit PNG (Sub filter, ordered dither against banding)."""
    h, w, _ = rgb.shape
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0 - 0.5
    dither = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w, None]
    img = np.clip(rgb * 255.0 + dither, 0, 255).astype(np.uint8)
    sub = img.astype(np.int16)
    sub[:, 1:] -= img[:, :-1].astype(np.int16)  # PNG filter type 1 (Sub)
    raw = np.concatenate([np.ones((h, 1), np.uint8), (sub % 256).astype(np.uint8).reshape(h, -1)], axis=1)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw.tobytes(), 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def grid() -> tuple[np.ndarray, np.ndarray]:
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    return x / W, y / H


def vgrad(y: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    pos = np.array([p for p, _ in stops])
    cols = np.array([c for _, c in stops], dtype=np.float64) / 255.0
    return np.stack([np.interp(y, pos, cols[:, k]) for k in range(3)], axis=-1)


def ridge(n: int, octaves: int, seed: int) -> np.ndarray:
    """1-D fractal noise in 0..1 (for mountain lines and aurora shapes)."""
    r = np.random.default_rng(seed)
    out = np.zeros(n)
    for o in range(octaves):
        k = 2 ** (o + 2)
        pts = r.random(k + 1)
        out += np.interp(np.linspace(0, k, n), np.arange(k + 1), pts) / 2 ** o
    return (out - out.min()) / (np.ptp(out) or 1)


def stars(img: np.ndarray, mask: np.ndarray, count: int, seed: int) -> None:
    r = np.random.default_rng(seed)
    ys, xs = r.integers(0, H, count), r.integers(0, W, count)
    keep = mask[ys, xs]
    b = r.uniform(0.35, 1.0, count)[keep]
    img[ys[keep], xs[keep]] = np.maximum(img[ys[keep], xs[keep]], b[:, None] * np.array([0.92, 0.95, 1.0]))


def scene_earthrise() -> np.ndarray:
    """Aurora curtains over the night-side limb of Earth, seen from orbit."""
    x, y = grid()
    img = vgrad(y, [(0, (4, 6, 18)), (0.6, (8, 12, 32)), (1, (10, 18, 40))])
    # Earth: a huge circle whose top edge is the limb
    cx, cy, R = 0.5, 2.35, 1.62
    d = np.sqrt(((x - cx) * W / H) ** 2 + (y - cy) ** 2) - R  # <0 inside Earth
    earth = d < 0
    stars(img, ~earth & (y < 0.75), 700, 1)
    night = vgrad(y, [(0.6, (14, 22, 44)), (1, (6, 10, 22))])
    img = np.where(earth[..., None], night, img)
    # thin blue atmosphere along the limb
    glow = np.exp(-np.abs(d) / 0.012)[..., None] * np.array([0.25, 0.55, 1.0])
    img += glow * 0.55 + np.exp(-np.maximum(d, 0) / 0.05)[..., None] * np.array([0.05, 0.12, 0.3]) * (~earth)[..., None]
    # aurora: vertical curtains rising from the limb, green at the base and violet on top
    shape = ridge(W, 5, 7)
    height = 0.10 + 0.22 * ridge(W, 3, 11)
    above = np.clip(-d, None, 0) * -1  # distance above the limb (0 inside Earth)
    fall = np.exp(-((above - 0.02) / (height[None, :] * 0.55)) ** 2) * (above > 0.004)
    rays = 0.6 + 0.22 * np.sin(x * 140 + 11 * shape[None, :]) + 0.18 * np.sin(x * 410 + 5 * ridge(W, 4, 13)[None, :])
    curtain = (0.4 + 0.6 * shape[None, :]) * fall * rays
    tint = np.where((above / height[None, :] > 0.6)[..., None], np.array([0.55, 0.3, 0.85]), np.array([0.2, 1.0, 0.55]))
    img += curtain[..., None] * tint * 0.7
    # faint city-light speckles on the night side
    r = np.random.default_rng(3)
    ys, xs = r.integers(int(0.8 * H), H, 400), r.integers(0, W, 400)
    ok = earth[ys, xs]
    img[ys[ok], xs[ok]] += np.array([0.5, 0.4, 0.2])
    return np.clip(img, 0, 1)


def scene_ocean_shore() -> np.ndarray:
    """Calm sea at dusk: low sun, soft swell lines, wet sand."""
    x, y = grid()
    horizon, shore = 0.46, 0.80
    sky = vgrad(y, [(0, (32, 46, 92)), (0.25, (92, 96, 150)), (0.40, (232, 158, 128)), (horizon, (250, 196, 150))])
    sun = np.exp(-(((x - 0.62) * W / H) ** 2 + (y - 0.40) ** 2) / 0.0025)
    sky += sun[..., None] * np.array([1.0, 0.8, 0.5]) * 0.6
    sea_t = (y - horizon) / (shore - horizon)
    sea = vgrad(sea_t, [(0, (198, 140, 132)), (0.15, (70, 92, 136)), (1, (28, 62, 96))])
    swell = np.sin(np.clip(y - horizon, 0, None) ** 0.6 * 90 + 3 * ridge(W, 3, 5)[None, :]) * np.clip(sea_t, 0, 1)
    sea += (swell > 0.92)[..., None] * 0.08
    glitter = np.exp(-((x - 0.62) * W / H) ** 2 / (0.004 + 0.05 * np.clip(sea_t, 0, 1))) * (swell > 0.6)
    sea += glitter[..., None] * np.array([1.0, 0.8, 0.55]) * 0.45
    foam_line = shore + 0.012 * np.sin(x * 9 + 2 * ridge(W, 3, 9)[None, :])
    sand = vgrad(y, [(shore, (140, 116, 104)), (1, (96, 78, 72))])
    img = np.where((y < horizon)[..., None], sky, np.where((y < foam_line)[..., None], sea, sand))
    img += (np.exp(-((y - foam_line) / 0.006) ** 2))[..., None] * 0.45
    return np.clip(img, 0, 1)


def scene_forest_stream() -> np.ndarray:
    """Forest and mountains at dusk, a stream catching the last light."""
    x, y = grid()
    img = vgrad(y, [(0, (40, 34, 78)), (0.30, (120, 78, 120)), (0.48, (238, 150, 110)), (0.6, (250, 190, 140))])
    stars(img, y < 0.22, 160, 4)
    layers = [(0.42, 0.16, (108, 82, 118), 21), (0.52, 0.12, (70, 56, 88), 22), (0.62, 0.10, (38, 34, 56), 23)]
    for base, amp, col, seed in layers:
        line = base - amp * ridge(W, 6, seed)
        img = np.where((y > line[None, :])[..., None], np.array(col) / 255.0, img)
    # stream: a winding band that reflects the sky
    centre = 0.5 + 0.18 * np.sin((y - 0.7) * 9) * (y > 0.7)
    width = 0.01 + 0.12 * np.clip((y - 0.7) / 0.3, 0, 1)
    stream = (np.abs(x - centre) < width) & (y > 0.7)
    refl = vgrad(1.25 - y, [(0.25, (90, 70, 110)), (0.55, (236, 160, 120))])
    img = np.where(stream[..., None], refl * 0.8, img)
    # pine silhouettes along both banks
    r = np.random.default_rng(8)
    for _ in range(46):
        px = r.uniform(0, 1)
        if abs(px - 0.5) < 0.12:
            continue
        base = r.uniform(0.74, 1.02)
        hgt = r.uniform(0.18, 0.38) * (0.6 + base - 0.74)
        half = hgt * 0.22 * (H / W)
        rel = (base - y) / hgt  # 0 at the base, 1 at the tip
        tooth = 0.85 + 0.15 * np.sin(rel * 40)
        tree = (rel >= 0) & (rel <= 1) & (np.abs(x - px) < half * (1 - rel) * tooth)
        img = np.where(tree[..., None], np.array([14, 18, 28]) / 255.0, img)
    return np.clip(img, 0, 1)


# ============================================================================ audio ==
def shaped_noise(lo: float, hi: float, tilt: float = 0.0, seed: int = 0) -> np.ndarray:
    """Band-limited noise built in the frequency domain, so it loops with no seam.
    tilt: spectral slope in dB/octave (−6 ≈ brown, −3 ≈ pink)."""
    r = np.random.default_rng(seed)
    f = np.fft.rfftfreq(N, 1 / SR)
    spec = r.normal(size=f.size) + 1j * r.normal(size=f.size)
    gain = np.zeros_like(f)
    band = (f >= lo) & (f <= hi)
    gain[band] = (np.maximum(f[band], 1.0) / max(lo, 1.0)) ** (tilt / 6.02)
    edge = 0.25  # soft band edges (octaves)
    gain *= np.clip(np.log2(np.maximum(f, 1e-9) / lo) / edge + 1, 0, 1) * np.clip(np.log2(hi / np.maximum(f, 1e-9)) / edge + 1, 0, 1)
    out = np.fft.irfft(spec * gain, n=N)
    return out / (np.abs(out).max() or 1)


def lfo(cycles: float, phase: float = 0.0) -> np.ndarray:
    """Slow modulation 0..1 with a whole number of cycles per loop (seamless)."""
    t = np.arange(N) / N
    return 0.5 + 0.5 * np.sin(2 * np.pi * cycles * t + phase)


def lowpass_circular(sig: np.ndarray, cutoff: float) -> np.ndarray:
    f = np.fft.rfftfreq(N, 1 / SR)
    return np.fft.irfft(np.fft.rfft(sig) / (1 + (f / cutoff) ** 4), n=N)


def write_wav(path: Path, sig: np.ndarray, peak: float = 0.6) -> None:
    sig = sig / (np.abs(sig).max() or 1) * peak
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((sig * 32767).astype("<i2").tobytes())


def sound_ocean() -> np.ndarray:
    """Waves: filtered noise whose level and brightness swell every ~7.5 s."""
    body = shaped_noise(60, 2500, -4.5, seed=11)
    hiss = shaped_noise(800, 6000, -3, seed=12)
    swell = lfo(10) ** 2.2 * 0.85 + 0.15            # 10 waves per 75 s loop
    wash = lfo(10, -0.9) ** 4                        # foam hiss just after each crest
    drift = 0.8 + 0.2 * lfo(3, 1.0)
    return body * swell * drift + hiss * wash * 0.35


def sound_rain() -> np.ndarray:
    """Steady soft rain plus scattered drops (drops wrap around the loop end)."""
    bed = shaped_noise(400, 9000, -2, seed=21) * (0.8 + 0.2 * lfo(5))
    drops = np.zeros(N)
    r = np.random.default_rng(22)
    t = np.arange(int(0.03 * SR)) / SR
    for _ in range(LOOP_S * 9):
        f = r.uniform(1500, 4500)
        ping = np.sin(2 * np.pi * f * t * (1 - 0.6 * t / t[-1])) * np.exp(-t * r.uniform(120, 260))
        start = int(r.integers(0, N))
        idx = (start + np.arange(ping.size)) % N
        drops[idx] += ping * r.uniform(0.05, 0.25)
    return bed * 0.7 + drops


def sound_wind() -> np.ndarray:
    """Wind in the trees: brown noise with slow gusts, plus a faint leaf rustle."""
    gust = 0.3 + 0.7 * (0.6 * lfo(4, 0.3) + 0.4 * lfo(9, 2.0))
    low = shaped_noise(40, 900, -6, seed=31) * gust
    rustle = shaped_noise(1500, 7000, -3, seed=32) * lfo(4, 0.8) ** 3 * 0.18
    return low + rustle


def music_pad() -> np.ndarray:
    """A slow ambient chord pad: 4 chords × 18.75 s, soft attack/release, crossfaded round the loop."""
    t = np.arange(N) / SR
    def hz(midi: float) -> float:  # snapped so each partial has a whole number of cycles per loop
        return round(440.0 * 2 ** ((midi - 69) / 12) * LOOP_S) / LOOP_S
    chords = [[45, 52, 57, 60, 64], [41, 48, 53, 57, 60], [43, 50, 55, 59, 62], [40, 47, 52, 55, 59]]  # Am F G Em
    seg = N // len(chords)
    pos = np.arange(N)
    out = np.zeros(N)
    for i, chord in enumerate(chords):
        centre = seg * i + seg / 2
        dist = np.minimum(np.abs(pos - centre), N - np.abs(pos - centre))  # circular distance
        env = np.clip(1.25 - dist / (seg * 0.62), 0, 1) ** 2               # overlapping cross-fades
        voice = np.zeros(N)
        for k, m in enumerate(chord):
            f = hz(m)
            det = round(f * 1.003 * LOOP_S) / LOOP_S  # slight chorus
            voice += (np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * det * t + k)
                      + 0.15 * np.sin(2 * np.pi * 2 * f * t)) / (1 + 0.3 * k)
        out += voice * env
    out = lowpass_circular(out, 1800)
    return out * (0.85 + 0.15 * lfo(5))


# ============================================================================= main ==
def main() -> None:
    SCENES.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)
    jobs_img = {"earthrise": scene_earthrise, "ocean-shore": scene_ocean_shore, "forest-stream": scene_forest_stream}
    for sid, fn in jobs_img.items():
        p = SCENES / f"{sid}.png"
        write_png(p, fn())
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size / 1024:.0f} KB")
    jobs_snd = {"ocean-shore-nature": sound_ocean, "rain-window-nature": sound_rain,
                "forest-stream-nature": sound_wind, "music-ambient-pad": music_pad}
    for name, fn in jobs_snd.items():
        p = AUDIO / f"{name}.wav"
        write_wav(p, fn())
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
