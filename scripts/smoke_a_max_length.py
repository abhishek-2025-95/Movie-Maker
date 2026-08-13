"""Smoke max single-shot Wan length via two-pass MoE (Approach A ceiling).

Ladder: 81 → 121 → 161 → 193 → 225 @ 480x832.
Stops at first hard failure after logging results.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config
from wan_two_pass_moe import two_pass_wan

log = logging.getLogger("smoke_a_max")

LENGTHS = [81, 121, 161, 193, 225]
WW, WH = 480, 832
STEPS = 10
CFG = 4.5
WORK = ROOT / "temp" / "smoke_a_max_length"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    WORK.mkdir(parents=True, exist_ok=True)
    still = ROOT / "temp" / "romance_wan_premium_v4" / "dx_rom_wan_s00_still.png"
    if not still.exists():
        still = ROOT / "temp" / "romance_wan_premium_v3" / "dx_rom_wan_s00_still.png"
    assert still.exists(), still

    results: list[tuple[int, str, float]] = []
    max_ok = 0
    for length in LENGTHS:
        out = WORK / f"dx_smoke_a_len{length}.mp4"
        prefix = f"dx_smoke_a_len{length}"
        sec = length / 16.0
        log.info("=== TRY length=%s (~%.1fs) %sx%s ===", length, sec, WW, WH)
        try:
            two_pass_wan(
                still,
                visual="couple under umbrella rain soft blinks readable faces cinematic",
                motion="static hold soft blinks rain streaks gentle ambient motion",
                prefix=prefix,
                seed=99 + length,
                neg=config.FLUX_NEGATIVE_PROMPT,
                out_mp4=out,
                ww=WW,
                wh=WH,
                length=length,
                steps=STEPS,
                cfg=CFG,
            )
            mb = out.stat().st_size / 1e6
            results.append((length, "OK", mb))
            max_ok = length
            log.info("OK length=%s size=%.2fMB path=%s", length, mb, out)
            (WORK / "max_ok.txt").write_text(f"{length}\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            results.append((length, f"FAIL:{exc}", 0.0))
            log.exception("FAIL length=%s: %s", length, exc)
            break

    print("=== LADDER RESULTS ===")
    for length, status, mb in results:
        print(f"length={length} (~{length/16:.1f}s) {status} mb={mb:.2f}")
    print(f"MAX_OK_LENGTH={max_ok}")
    print(f"MAX_OK_SECONDS={max_ok/16.0 if max_ok else 0:.2f}")


if __name__ == "__main__":
    main()
