#!/usr/bin/env python3
"""Parse per-sample boottime artifacts into a long-form pandas DataFrame.

Reads what `make run_boottime_{native,gramine,kata}` deposits under
Benchmarks/Boottime/{native,gramine,kata}/result/ and returns one row per
(system, sample, step). Step durations are chronologically non-overlapping
within a sample, so the frame is ready for a stacked plot.

Step labels match the canonical names used by Benchmarks/Boottime/plot.py.
"""

import os
import re
import sys
from pathlib import Path

import pandas as pd

DEFAULT_ROOT = Path(__file__).resolve().parent.resolve().parent / "Benchmarks" / "Boottime"

STEP_EARLY = "Early runtime"
STEP_QEMU = "VMM (QEMU)"
STEP_OVMF = "Firmware (OVMF)"
STEP_LINUX = "OS/Guest-OS"
STEP_BOOT_COMBINED = "VMM+OVMF+OS"  # fallback when OVMF markers absent
STEP_RUNTIME = "Runtime"
STEP_INVOKE = "Invoke"


def _read_lines(path):
    return Path(path).read_text().splitlines()


# ---------- native -----------------------------------------------------------

def _parse_native(root):
    rows, warnings = [], []
    f = root / "native" / "result"
    if not f.exists():
        warnings.append(f"native: missing {f}")
        return rows, warnings
    for i, line in enumerate(_read_lines(f)):
        line = line.strip()
        if not line:
            continue
        try:
            ms = float(line)
        except ValueError:
            warnings.append(f"native: non-numeric line {i} in {f}: {line!r}")
            continue
        rows.append({"system": "native", "sample": i,
                     "step": STEP_INVOKE, "time_ms": ms})
    return rows, warnings


# ---------- gramine ----------------------------------------------------------

def _parse_gramine_sample(text):
    if len(text) < 3:
        raise ValueError(f"only {len(text)} non-empty lines, expected 3")
    start_ns = int(text[0].strip())
    if "Time: " not in text[1]:
        raise ValueError(f"line 1 missing 'Time: ' marker: {text[1]!r}")
    mid_ns = int(text[1].split("Time: ")[1].strip()) * 1000  # us -> ns
    end_ns = int(text[2].strip())
    if not (start_ns <= mid_ns <= end_ns):
        raise ValueError(
            f"timestamps not monotonic: {start_ns} -> {mid_ns} -> {end_ns}")
    return {
        STEP_RUNTIME: (mid_ns - start_ns) / 1e6,
        STEP_INVOKE:  (end_ns - mid_ns) / 1e6,
    }


def _parse_gramine(root):
    rows, warnings = [], []
    d = root / "gramine" / "result"
    if not d.is_dir():
        warnings.append(f"gramine: missing dir {d}")
        return rows, warnings
    files = sorted(d.glob("res-*.txt"))
    if not files:
        warnings.append(f"gramine: no res-*.txt files in {d}")
        return rows, warnings
    for path in files:
        m = re.search(r"res-(\d+)\.txt$", path.name)
        sample = int(m.group(1)) if m else -1
        try:
            steps = _parse_gramine_sample(_read_lines(path))
        except Exception as e:
            warnings.append(f"gramine: failed to parse {path.name}: {e}")
            continue
        for step, ms in steps.items():
            rows.append({"system": "gramine", "sample": sample,
                         "step": step, "time_ms": ms})
    return rows, warnings


# ---------- kata -------------------------------------------------------------

def _kata_first_event(text, substr):
    for line in text:
        if substr in line:
            return int(line.split(":", 1)[0])
    raise ValueError(f"marker {substr!r} not found")


def _kata_se(text):
    start = end = None
    for line in text:
        if line.startswith("Start:"):
            start = int(line.split(":", 1)[1].strip())
        elif line.startswith("End:"):
            end = int(line.split(":", 1)[1].strip())
    if start is None or end is None:
        raise ValueError("se file missing 'Start:' or 'End:'")
    return start, end


def _kata_log_event(text, substr):
    from dateutil import parser as _dp
    for line in reversed(text):
        if substr not in line:
            continue
        try:
            l = line.split('time="')[1]
            l = l.split('Z" level')[0]
            sec_str, frac_str = l.split(".")
            sec_ns = int(_dp.isoparse(sec_str).timestamp()) * 1_000_000_000
            # frac_str is variable-length fractional seconds (e.g. "67989"
            # means 0.67989s, not 67989 ns); pad to nanoseconds.
            frac_ns = int(frac_str.ljust(9, "0")[:9])
            return sec_ns + frac_ns
        except (IndexError, ValueError) as e:
            raise ValueError(f"log line for {substr!r} unparseable: {e}")
    raise ValueError(f"log marker {substr!r} not found")


def _parse_kata_sample(res_path, se_path, log_path):
    """Return (steps_dict, mode_str). `mode_str` is "full" when the bpftrace
    OVMF port-0x50/0x52 markers were found, else "coarse" when only QEMU+log
    events were available. Both modes produce non-overlapping segments
    covering Start..End from the se file."""
    res = _read_lines(res_path)
    se = _read_lines(se_path)
    log = _read_lines(log_path)

    qemu_start = _kata_first_event(res, "QEMU: main")
    se_start, se_end = _kata_se(se)
    agent_started = _kata_log_event(log, "Agent started in the sandbox")
    mgmt_inited = _kata_log_event(log, "kata management inited")

    try:
        ovmf_start = _kata_first_event(res, ": 50")
        ovmf_end = _kata_first_event(res, ": 52")
    except ValueError:
        return {
            STEP_EARLY:         (qemu_start - se_start) / 1e6,
            STEP_BOOT_COMBINED: (agent_started - qemu_start) / 1e6,
            STEP_RUNTIME:       (mgmt_inited - agent_started) / 1e6,
            STEP_INVOKE:        (se_end - mgmt_inited) / 1e6,
        }, "coarse"

    return {
        STEP_EARLY:   (qemu_start - se_start) / 1e6,
        STEP_QEMU:    (ovmf_start - qemu_start) / 1e6,
        STEP_OVMF:    (ovmf_end - ovmf_start) / 1e6,
        STEP_LINUX:   (agent_started - ovmf_end) / 1e6,
        STEP_RUNTIME: (mgmt_inited - agent_started) / 1e6,
        STEP_INVOKE:  (se_end - mgmt_inited) / 1e6,
    }, "full"


def _parse_kata(root):
    rows, warnings = [], []
    d = root / "kata" / "result"
    if not d.is_dir():
        warnings.append(f"kata: missing dir {d}")
        return rows, warnings
    res_files = sorted(d.glob("res-*.txt"))
    if not res_files:
        warnings.append(f"kata: no res-*.txt files in {d}")
        return rows, warnings
    modes = []
    for res_path in res_files:
        m = re.search(r"res-(\d+)\.txt$", res_path.name)
        if not m:
            continue
        i = int(m.group(1))
        se_path = d / f"se-{i}.txt"
        log_path = d / f"log-{i}.txt"
        if not se_path.exists() or not log_path.exists():
            warnings.append(
                f"kata sample {i}: missing companion file(s) "
                f"(se exists={se_path.exists()}, log exists={log_path.exists()})")
            continue
        try:
            steps, mode = _parse_kata_sample(res_path, se_path, log_path)
        except Exception as e:
            warnings.append(f"kata sample {i}: {e}")
            continue
        modes.append(mode)
        for step, ms in steps.items():
            rows.append({"system": "kata", "sample": i,
                         "step": step, "time_ms": ms})
    if modes and all(m == "coarse" for m in modes):
        warnings.append(
            "kata: OVMF port-0x50/0x52 markers absent in every res-*.txt — "
            f"fell back to coarse breakdown ({STEP_EARLY}, {STEP_BOOT_COMBINED}, "
            f"{STEP_RUNTIME}, {STEP_INVOKE}); QEMU/OVMF/Linux not separable")
    elif "coarse" in modes:
        n = sum(1 for m in modes if m == "coarse")
        warnings.append(
            f"kata: {n} sample(s) fell back to coarse breakdown (no OVMF markers)")
    return rows, warnings


# ---------- public api -------------------------------------------------------

def parse(root: os.PathLike = DEFAULT_ROOT, *, verbose: bool = True) -> pd.DataFrame:
    """Return a long-form DataFrame with columns: system, sample, step, time_ms.

    One row per duration sample. Missing/broken inputs produce warnings on
    stderr (when verbose) and are silently dropped from the frame.
    """
    root = Path(root)
    all_rows, all_warnings = [], []
    for fn in (_parse_native, _parse_gramine, _parse_kata):
        rows, warnings = fn(root)
        all_rows.extend(rows)
        all_warnings.extend(warnings)
    if verbose and all_warnings:
        print("[boottime_parser] warnings:", file=sys.stderr)
        for w in all_warnings:
            print(f"  - {w}", file=sys.stderr)
    return pd.DataFrame(all_rows, columns=["system", "sample", "step", "time_ms"])


if __name__ == "__main__":
    df = parse()
    print(df)
    if not df.empty:
        print()
        print(df.groupby(["system", "step"])["time_ms"]
                .agg(["count", "mean", "std"]))
