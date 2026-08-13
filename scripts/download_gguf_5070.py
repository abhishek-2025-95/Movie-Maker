"""Resumable GGUF downloads with live % progress for RTX 5070 profile."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

from huggingface_hub import get_hf_file_metadata, hf_hub_download, hf_hub_url

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "temp" / "gguf_download_progress.txt"
UNET = Path(r"C:\ComfyUI\models\unet")
TE = Path(r"C:\ComfyUI\models\text_encoders")
CLIP = Path(r"C:\ComfyUI\models\clip")
VAE = Path(r"C:\ComfyUI\models\vae")

EXPECTED = {
    "flux1-dev-Q5_K_S.gguf": 8_285_267_232,
    "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf": 9_650_000_000,
    "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf": 9_650_000_000,
    "t5xxl_fp8_e4m3fn.safetensors": 4_890_000_000,
    "clip_l.safetensors": 246_000_000,
    "ae.safetensors": 335_000_000,
}

KNOWN_ETAGS = {
    "flux1-dev-Q5_K_S.gguf": "aa76146ca0f1b09c67e0c3fcef18be3a375837ecd5aaa021d3e9ebc558bd68f9",
    "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf": "0c170a4ae4228a7d30a2cb4dded6eb2bc48ccb1ce761445bb092ff7c5dd4f47b",
}

JOBS: list[tuple[str, str, Path, float]] = [
    ("city96/FLUX.1-dev-gguf", "flux1-dev-Q5_K_S.gguf", UNET, 7.5),
    ("bullerwins/Wan2.2-I2V-A14B-GGUF", "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf", UNET, 8.5),
    ("bullerwins/Wan2.2-I2V-A14B-GGUF", "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf", UNET, 8.5),
    ("comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn.safetensors", TE, 4.0),
    ("comfyanonymous/flux_text_encoders", "clip_l.safetensors", TE, 0.2),
]

# Prefer curl for big files — HF multipart/XET keeps hanging on this machine.
CURL_MIN_BYTES = 500_000_000
STALL_SECS = 120
MAX_RETRIES = 12


def _write_status(lines: list[str]) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cache_dir(dest_dir: Path) -> Path:
    return dest_dir / ".cache" / "huggingface" / "download"


def _part_path(dest_dir: Path, filename: str) -> Path:
    return dest_dir / f"{Path(filename).name}.part"


def _resolve_etag(repo: str, filename: str) -> str | None:
    if filename in KNOWN_ETAGS:
        return KNOWN_ETAGS[filename]
    try:
        meta = get_hf_file_metadata(hf_hub_url(repo_id=repo, filename=filename))
        etag = (meta.etag or "").strip('"')
        if etag:
            KNOWN_ETAGS[filename] = etag
            return etag
    except Exception:
        return KNOWN_ETAGS.get(filename)
    return None


def _shards_for_etag(cache: Path, etag: str) -> list[Path]:
    frag = etag[:16]
    return [p for p in cache.glob("*.incomplete") if frag in p.name]


def _purge_hf_shards(dest_dir: Path, etag: str | None) -> None:
    """Remove broken HF multipart leftovers (cannot assemble reliably)."""
    if not etag:
        return
    cache = _cache_dir(dest_dir)
    if not cache.exists():
        return
    removed = 0
    freed = 0
    for p in _shards_for_etag(cache, etag):
        try:
            freed += p.stat().st_size
            p.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pass
    for extra in cache.glob(f"*{etag[:16]}*"):
        try:
            if extra.is_file():
                freed += extra.stat().st_size
                extra.unlink(missing_ok=True)
                removed += 1
        except OSError:
            pass
    if removed:
        print(f"[cleanup] purged {removed} HF shard files ({freed / 1e9:.1f} GB)", flush=True)


def _partial_bytes(dest_dir: Path, filename: str, etag: str | None) -> int:
    """Prefer the curl .part / final file — those are trustworthy."""
    final = dest_dir / Path(filename).name
    if final.exists():
        return final.stat().st_size
    part = _part_path(dest_dir, filename)
    if part.exists():
        return part.stat().st_size
    # Fallback: largest single HF incomplete (not sum — avoids 100% fake)
    if etag:
        cache = _cache_dir(dest_dir)
        if cache.exists():
            shards = _shards_for_etag(cache, etag)
            if shards:
                return max(p.stat().st_size for p in shards)
    return 0


def _activity_token(dest_dir: Path, filename: str, etag: str | None) -> str:
    """Changes whenever on-disk download data actually moves."""
    bits: list[str] = []
    for p in (dest_dir / Path(filename).name, _part_path(dest_dir, filename)):
        if p.exists():
            st = p.stat()
            bits.append(f"{p.name}:{st.st_size}:{st.st_mtime_ns}")
    if etag:
        cache = _cache_dir(dest_dir)
        if cache.exists():
            for p in sorted(_shards_for_etag(cache, etag), key=lambda x: x.name):
                try:
                    st = p.stat()
                    bits.append(f"{p.name}:{st.st_size}:{st.st_mtime_ns}")
                except OSError:
                    pass
    return "|".join(bits)


def have(path: Path, min_gb: float) -> bool:
    return path.exists() and path.stat().st_size >= min_gb * (1024**3)


def _pct(done: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return min(99.9, 100.0 * done / total)


class ProgressMonitor(threading.Thread):
    def __init__(
        self,
        filename: str,
        dest_dir: Path,
        job_index: int,
        job_total: int,
        etag: str | None,
        expected: int,
    ):
        super().__init__(daemon=True)
        self.filename = filename
        self.dest_dir = dest_dir
        self.job_index = job_index
        self.job_total = job_total
        self.etag = etag
        self.expected = expected or EXPECTED.get(filename, 0)
        self._halt = threading.Event()
        self.last_bytes = -1
        self.last_token = ""
        self.last_move_t = time.time()
        self.stall = False
        self.mbps = 0.0
        self._prev_t = time.time()
        self._prev_b = -1

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            nbytes = _partial_bytes(self.dest_dir, self.filename, self.etag)
            token = _activity_token(self.dest_dir, self.filename, self.etag)
            now = time.time()
            if self._prev_b < 0:
                self._prev_b = nbytes
                self._prev_t = now
                self.mbps = 0.0
            else:
                dt = max(0.001, now - self._prev_t)
                self.mbps = max(0.0, ((nbytes - self._prev_b) / dt) / (1024 * 1024))
                self._prev_t = now
                self._prev_b = nbytes

            if token != self.last_token or nbytes != self.last_bytes:
                self.last_token = token
                self.last_bytes = nbytes
                self.last_move_t = now
                self.stall = False
            elif now - self.last_move_t >= STALL_SECS:
                self.stall = True

            final = self.dest_dir / self.filename
            if final.exists() and final.stat().st_size >= self.expected * 0.95:
                pct = 100.0
            else:
                pct = _pct(nbytes, self.expected) if self.expected else 0.0

            overall_base = (self.job_index / self.job_total) * 100.0
            overall = overall_base + (pct / self.job_total)
            bar_w = 28
            filled = int(bar_w * pct / 100.0)
            bar = "#" * filled + "-" * (bar_w - filled)
            stall_tag = "  STALL" if self.stall else ""
            line = (
                f"[{self.job_index + 1}/{self.job_total}] {self.filename} "
                f"|{bar}| {pct:5.1f}%  {nbytes / 1e9:.2f}/{self.expected / 1e9:.2f} GB"
                f"  {self.mbps:4.1f} MB/s  (overall ~{overall:4.1f}%){stall_tag}"
            )
            print(line, flush=True)
            _write_status(
                [
                    f"file={self.filename}",
                    f"file_pct={pct:.1f}",
                    f"file_gb={nbytes / 1e9:.2f}",
                    f"file_total_gb={self.expected / 1e9:.2f}",
                    f"speed_mbps={self.mbps:.2f}",
                    f"stall={'1' if self.stall else '0'}",
                    f"job={self.job_index + 1}/{self.job_total}",
                    f"overall_pct={overall:.1f}",
                    f"status={'STALL' if self.stall else 'RUNNING'}",
                    f"bytes={nbytes}",
                    f"updated={time.strftime('%H:%M:%S')}",
                    line,
                ]
            )
            self._halt.wait(2.0)


def _curl_available() -> bool:
    try:
        r = subprocess.run(["curl.exe", "--version"], capture_output=True, text=True, check=False)
        return r.returncode == 0
    except OSError:
        return False


def _one_shot_curl(repo: str, filename: str, dest_dir: Path) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / Path(filename).name
    part = _part_path(dest_dir, filename)
    url = hf_hub_url(repo_id=repo, filename=filename)
    # Resolve size
    try:
        meta = get_hf_file_metadata(url)
        expected = int(meta.size or 0)
    except Exception:
        expected = EXPECTED.get(filename, 0)

    print(f"[curl] {url}", flush=True)
    print(f"[curl] resume -> {part} (expect {expected / 1e9:.2f} GB)", flush=True)

    cmd = [
        "curl.exe",
        "-L",
        "--fail",
        "--retry",
        "5",
        "--retry-delay",
        "3",
        "--connect-timeout",
        "30",
        "-C",
        "-",
        "-o",
        str(part),
        url,
    ]
    # Pass HF token if present (gated repos)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        cmd[1:1] = ["-H", f"Authorization: Bearer {token}"]

    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"curl exit {proc.returncode}")
    if not part.exists():
        raise RuntimeError("curl finished but part file missing")
    if expected and part.stat().st_size < expected * 0.98:
        raise RuntimeError(
            f"curl incomplete: {part.stat().st_size} < {expected}"
        )
    part.replace(out)
    return out


def _one_shot_hf(repo: str, filename: str, dest_dir: Path) -> Path:
    return Path(hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest_dir)))


def pull(repo: str, filename: str, dest_dir: Path, min_gb: float, job_index: int, job_total: int) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / Path(filename).name
    if have(out, min_gb):
        msg = f"[=] {out.name} already present ({out.stat().st_size / 1e9:.2f} GB) — 100%"
        print(msg, flush=True)
        _write_status(
            [
                f"file={filename}",
                "file_pct=100.0",
                f"file_gb={out.stat().st_size / 1e9:.2f}",
                f"job={job_index + 1}/{job_total}",
                f"overall_pct={((job_index + 1) / job_total) * 100:.1f}",
                "status=RUNNING",
                "stall=0",
                msg,
            ]
        )
        return out

    etag = _resolve_etag(repo, filename)
    expected = EXPECTED.get(filename, 0)
    try:
        meta = get_hf_file_metadata(hf_hub_url(repo_id=repo, filename=filename))
        if meta.size:
            expected = int(meta.size)
            EXPECTED[filename] = expected
    except Exception:
        pass

    use_curl = _curl_available() and expected >= CURL_MIN_BYTES
    if use_curl:
        # Broken HF multipart cache cannot be assembled — free the disk and use curl.
        _purge_hf_shards(dest_dir, etag)
        # Reset misleading HWM
        hwm = STATUS.parent / f"gguf_hwm_{Path(filename).name}.txt"
        try:
            hwm.unlink(missing_ok=True)
        except OSError:
            pass

    print(
        f"[+] START {repo} :: {filename} (expect {expected / 1e9:.2f} GB) "
        f"via={'curl' if use_curl else 'hf_hub'}",
        flush=True,
    )
    last_err: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        lock = _cache_dir(dest_dir) / f"{filename}.lock"
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass

        mon = ProgressMonitor(filename, dest_dir, job_index, job_total, etag, expected)
        mon.start()

        mode = "curl" if use_curl else "hf"
        cmd = [
            sys.executable,
            "-u",
            str(Path(__file__).resolve()),
            f"--one-shot-{mode}",
            repo,
            filename,
            str(dest_dir),
        ]
        env = os.environ.copy()
        env["HF_HUB_DISABLE_XET"] = "1"
        env["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
        print(f"[attempt {attempt}/{MAX_RETRIES}] worker mode={mode}", flush=True)
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)

        try:
            while proc.poll() is None:
                if mon.stall:
                    print(
                        f"[watchdog] no disk activity for {STALL_SECS}s — kill & retry",
                        flush=True,
                    )
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        pass
                    last_err = RuntimeError(f"stalled {STALL_SECS}s")
                    break
                time.sleep(2.0)
            else:
                if proc.returncode == 0 and have(out, min_gb):
                    mon.stop()
                    mon.join(timeout=3)
                    print(
                        f"[OK] {out.name} 100% ({out.stat().st_size / 1e9:.2f}/"
                        f"{expected / 1e9:.2f} GB)",
                        flush=True,
                    )
                    return out
                last_err = RuntimeError(f"worker exit {proc.returncode}")
                print(f"[retry] attempt {attempt} failed: {last_err}", flush=True)
        finally:
            if proc.poll() is None:
                proc.kill()
            mon.stop()
            mon.join(timeout=3)

        time.sleep(min(3 * attempt, 15))

    raise RuntimeError(f"Failed to download {filename} after {MAX_RETRIES} attempts: {last_err}")


def main() -> int:
    if len(sys.argv) >= 5 and sys.argv[1] in {"--one-shot", "--one-shot-hf"}:
        repo, filename, dest = sys.argv[2], sys.argv[3], Path(sys.argv[4])
        path = _one_shot_hf(repo, filename, dest)
        print(f"[one-shot-hf] wrote {path}", flush=True)
        return 0
    if len(sys.argv) >= 5 and sys.argv[1] == "--one-shot-curl":
        repo, filename, dest = sys.argv[2], sys.argv[3], Path(sys.argv[4])
        path = _one_shot_curl(repo, filename, dest)
        print(f"[one-shot-curl] wrote {path}", flush=True)
        return 0

    for p in (UNET, TE, CLIP, VAE):
        p.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage("C:/").free / 1e9
    print(f"C free GB={free:.1f}", flush=True)
    print("Large files use curl -C - resume (HF multipart disabled)", flush=True)

    total = len(JOBS) + 1
    for i, (repo, name, dest, min_gb) in enumerate(JOBS):
        pull(repo, name, dest, min_gb, i, total)

    clip = TE / "clip_l.safetensors"
    if clip.exists():
        try:
            shutil.copy2(clip, CLIP / clip.name)
        except OSError as exc:
            print("clip copy warn", exc, flush=True)

    try:
        pull("black-forest-labs/FLUX.1-dev", "ae.safetensors", VAE, 0.2, len(JOBS), total)
    except Exception as exc:  # noqa: BLE001
        print(f"AE gated/fail (non-fatal): {exc}", flush=True)
        print("Continuing — Flux FP8 stills remain available without AE.", flush=True)

    _write_status(
        [
            "file=DONE",
            "file_pct=100.0",
            "overall_pct=100.0",
            "status=DOWNLOADS_DONE",
            "stall=0",
            f"updated={time.strftime('%H:%M:%S')}",
        ]
    )
    print("DOWNLOADS_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
