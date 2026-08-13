"""Live % monitor for GGUF downloads — run in a second external window."""
from __future__ import annotations

import time
from pathlib import Path

STATUS = Path(__file__).resolve().parents[1] / "temp" / "gguf_download_progress.txt"
LOG = Path(__file__).resolve().parents[1] / "temp" / "gguf_download_live.log"

UNET = Path(r"C:\ComfyUI\models\unet")
TE = Path(r"C:\ComfyUI\models\text_encoders")
VAE = Path(r"C:\ComfyUI\models\vae")

# Same etag/size map as downloader — used if status file is missing
TRACKED = [
    ("flux1-dev-Q5_K_S.gguf", UNET, 8_285_267_232, "aa76146ca0f1b09c67e0c3fcef18be3a375837ecd5aaa021d3e9ebc558bd68f9"),
    ("wan2.2_i2v_high_noise_14B_Q4_K_M.gguf", UNET, 9_650_000_000, "0c170a4ae4228a7d30a2cb4dded6eb2bc48ccb1ce761445bb092ff7c5dd4f47b"),
    ("wan2.2_i2v_low_noise_14B_Q4_K_M.gguf", UNET, 9_650_000_000, None),
    ("t5xxl_fp8_e4m3fn.safetensors", TE, 4_890_000_000, None),
    ("clip_l.safetensors", TE, 246_000_000, None),
    ("ae.safetensors", VAE, 335_000_000, None),
]


def _parse_status(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("["):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _is_main_incomplete(path: Path, etag: str) -> bool:
    return path.name.endswith(f".{etag}.incomplete")


def _partial_bytes(dest: Path, filename: str, etag: str | None, expected: int) -> int:
    final = dest / filename
    if final.exists():
        return final.stat().st_size
    part = dest / f"{filename}.part"
    if part.exists():
        return part.stat().st_size
    cache = dest / ".cache" / "huggingface" / "download"
    if not cache.exists() or not etag:
        return 0
    frag = etag[:16]
    shards = [p for p in cache.glob("*.incomplete") if frag in p.name]
    if not shards:
        return 0
    return min(expected, max(p.stat().st_size for p in shards)) if expected else max(
        p.stat().st_size for p in shards
    )


def _bar(pct: float, width: int = 40) -> str:
    filled = int(width * max(0.0, min(100.0, pct)) / 100.0)
    return "#" * filled + "-" * (width - filled)


def main() -> None:
    print("Watching", STATUS)
    print("Ctrl+C to stop monitor (download keeps running).\n")
    last_bytes = -1
    last_move_t = time.time()
    prev_b = 0
    prev_t = time.time()

    while True:
        file_name = ""
        file_pct = 0.0
        file_gb = 0.0
        file_total = 0.0
        overall = 0.0
        speed = 0.0
        job = ""
        line = ""
        status = "RUNNING"
        stall = False
        nbytes = 0

        if STATUS.exists():
            text = STATUS.read_text(encoding="utf-8", errors="replace").strip()
            kv = _parse_status(text)
            status = kv.get("status", "RUNNING")
            file_name = kv.get("file", "")
            stall = kv.get("stall", "0") == "1" or status == "STALL"
            try:
                file_pct = float(kv.get("file_pct", "0") or 0)
                file_gb = float(kv.get("file_gb", "0") or 0)
                file_total = float(kv.get("file_total_gb", "0") or 0)
                overall = float(kv.get("overall_pct", "0") or 0)
                speed = float(kv.get("speed_mbps", "0") or 0)
                nbytes = int(float(kv.get("bytes", "0") or 0))
            except ValueError:
                pass
            job = kv.get("job", "")
            for ln in text.splitlines():
                if ln.startswith("["):
                    line = ln

        # Disk fallback if status missing / nonsense (>100% inflation from old bug)
        if (not file_name or file_pct >= 99.9 or file_gb > file_total > 0) and status != "DOWNLOADS_DONE":
            for name, dest, total, etag in TRACKED:
                if (dest / name).exists() and (dest / name).stat().st_size >= total * 0.95:
                    continue
                b = _partial_bytes(dest, name, etag, total)
                lock = dest / ".cache" / "huggingface" / "download" / f"{name}.lock"
                if b > 0 or lock.exists() or not file_name:
                    file_name = name
                    nbytes = b
                    file_gb = b / 1e9
                    file_total = total / 1e9
                    file_pct = min(99.9, 100.0 * b / total) if total else 0.0
                    # rough overall from position in list
                    idx = next(i for i, t in enumerate(TRACKED) if t[0] == name)
                    overall = (idx / len(TRACKED)) * 100.0 + file_pct / len(TRACKED)
                    break

        now = time.time()
        if nbytes and nbytes != last_bytes:
            if last_bytes >= 0 and now > prev_t:
                speed = max(speed, ((nbytes - prev_b) / max(0.001, now - prev_t)) / (1024 * 1024))
            last_bytes = nbytes
            last_move_t = now
            prev_b = nbytes
            prev_t = now
            stall = False
        elif nbytes and now - last_move_t >= 90:
            stall = True
            status = "STALL"

        # Always redraw so clock / speed / stall state update even at same %
        print("\033[2J\033[H", end="")
        print("=== DirectorX GGUF download monitor ===")
        print()
        print(f"  CURRENT FILE : {file_name or '(waiting)'}")
        if job:
            print(f"  JOB          : {job}")
        print()
        print(f"  FILE PROGRESS: {file_pct:6.1f} %")
        print(f"  |{_bar(file_pct)}|")
        if file_total > 0:
            print(f"  {file_gb:.2f} / {file_total:.2f} GB")
        print(f"  SPEED        : {speed:6.1f} MB/s")
        print()
        print(f"  OVERALL      : {overall:6.1f} %")
        print(f"  |{_bar(overall)}|")
        print()
        if stall:
            print("  !!! STALLED — downloader should auto-retry within ~90s !!!")
            print()
        if line:
            print(line)
        if LOG.exists():
            tail = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            print("\n--- download log (tail) ---")
            print("\n".join(tail))
        print(f"\nupdated {time.strftime('%H:%M:%S')}  status={status}")

        if status == "DOWNLOADS_DONE":
            print("\nDownloads finished.")
            break
        time.sleep(1.0)


if __name__ == "__main__":
    main()
