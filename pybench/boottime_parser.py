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

_PROJECT_ROOT = Path(__file__).resolve().parent.resolve().parent
DEFAULT_ROOT = _PROJECT_ROOT / "Benchmarks" / "Boottime"
ATTESTATION_CSV = _PROJECT_ROOT / "Benchmarks" / "Attestation" / "results.csv"
ATTESTATION_BREAKDOWN_CVM_CSV = (
    _PROJECT_ROOT / "Benchmarks" / "Attestation" / "breakdown" / "cvm" / "result.csv")

STEP_EARLY = "Early runtime"
STEP_QEMU = "VMM (QEMU)"
STEP_OVMF = "Firmware (OVMF)"
STEP_LINUX = "OS/Guest-OS"
STEP_BOOT_COMBINED = "VMM+OVMF+OS"  # fallback when OVMF markers absent
STEP_ATTESTATION = "Attestation"    # SVSM Monitor cold attestation (Wallet only)
STEP_RUNTIME = "Runtime"
STEP_INVOKE = "Invoke"

# Wallet systems (in measure_startup output) that get the Attestation step
# from Benchmarks/Attestation/results.csv attached. Extend as slick/trustlet land.
WALLET_ATTEST_SYSTEMS = ("cvm",)


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


# ---------- measure_startup (pybench/measure_startup.py) ---------------------

def _parse_bpftrace_events(text):
    """Yield (ts_ns, event_id_or_None, event_name) from a boot_time_eval.bt log."""
    for line in text:
        line = line.strip()
        if not line or line.startswith("Attaching") or line == "INITED":
            continue
        if ":" not in line:
            continue
        ts_str, rest = line.split(":", 1)
        try:
            ts = int(ts_str)
        except ValueError:
            continue
        rest = rest.strip()
        parts = rest.split(None, 1)
        if parts and parts[0].isdigit():
            yield ts, int(parts[0]), parts[1] if len(parts) > 1 else ""
        else:
            yield ts, None, rest


def _first_by_id(events, target_id):
    for ts, eid, _ in events:
        if eid == target_id:
            return ts
    return None


def _first_by_name(events, target_name):
    for ts, _, name in events:
        if name == target_name:
            return ts
    return None


def _pick_valid(*candidates, lo, hi):
    """Return the first candidate timestamp in [lo, hi] (and non-zero)."""
    for ts in candidates:
        if ts is not None and ts != 0 and lo <= ts <= hi:
            return ts
    return None


def _parse_measure_startup_sample(text):
    events = list(_parse_bpftrace_events(text))
    qemu_start = _first_by_name(events, "QEMU: main")
    if qemu_start is None:
        raise ValueError("missing 'QEMU: main' marker")
    systemd_end = _first_by_id(events, 100)
    if systemd_end is None:
        raise ValueError("missing event 100 (Linux: systemd init end)")
    if not (qemu_start <= systemd_end):
        raise ValueError(
            f"timestamps not monotonic: qemu={qemu_start} systemd={systemd_end}")

    # OVMF boundaries: prefer the SVSM-specific port-0xf4 markers (CVM); fall
    # back to KVM Entry (first guest entry ≈ OVMF start) and the OVMF uprobe
    # "last POST" marker (≈ ExitBootServices) for stock-OVMF VM runs.
    kvm_entry = _first_by_name(events, "KVM Entry: main")
    ovmf_post = _first_by_name(
        events, "OVMF: last POST (ExitBootServices proxy)")
    port_50 = _first_by_id(events, 50)
    port_52 = _first_by_id(events, 52)

    ovmf_start = _pick_valid(port_50, kvm_entry, lo=qemu_start, hi=systemd_end)
    ovmf_end = _pick_valid(ovmf_post, port_52, lo=qemu_start, hi=systemd_end)

    steps = {}
    if ovmf_start is not None and ovmf_end is not None and ovmf_start <= ovmf_end:
        steps[STEP_QEMU] = (ovmf_start - qemu_start) / 1e6
        steps[STEP_OVMF] = (ovmf_end - ovmf_start) / 1e6
        steps[STEP_LINUX] = (systemd_end - ovmf_end) / 1e6
        mode = "full"
    else:
        steps[STEP_BOOT_COMBINED] = (systemd_end - qemu_start) / 1e6
        mode = "coarse"

    invoke_start = _first_by_id(events, 107)
    invoke_end = _first_by_id(events, 108)
    if invoke_start is not None and invoke_end is not None \
            and systemd_end <= invoke_start <= invoke_end:
        steps[STEP_RUNTIME] = (invoke_start - systemd_end) / 1e6
        steps[STEP_INVOKE] = (invoke_end - invoke_start) / 1e6
    return steps, mode


def _parse_iomgr_mirror_sample(text):
    """STARTUP lines from a *.mirror file (one task per line).

    Format: 'STARTUP <name> <duration_seconds>'. The header row (name='name')
    and the aggregate 'total' row are skipped so steps don't double-count.
    """
    steps = {}
    for line in text:
        line = line.strip()
        if not line.startswith("STARTUP "):
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        name = parts[1]
        if name in ("name", "total"):
            continue
        try:
            steps[name] = float(parts[2]) * 1000.0
        except ValueError:
            continue
    return steps


def _parse_measure_startup(results_dir):
    rows, warnings = [], []
    d = Path(results_dir)
    if not d.is_dir():
        warnings.append(f"measure-startup: missing dir {d}")
        return rows, warnings
    for system in ("vm", "cvm"):
        files = sorted(d.glob(f"startup_{system}_rep*.log"))
        if not files:
            warnings.append(
                f"measure-startup: no startup_{system}_rep*.log files in {d}")
            continue
        modes, no_invoke = [], 0
        for path in files:
            m = re.search(rf"startup_{system}_rep(\d+)\.log$", path.name)
            sample = int(m.group(1)) if m else -1
            try:
                steps, mode = _parse_measure_startup_sample(_read_lines(path))
            except Exception as e:
                warnings.append(f"measure-startup {system} {path.name}: {e}")
                continue
            modes.append(mode)
            if STEP_INVOKE not in steps:
                no_invoke += 1
            for step, ms in steps.items():
                rows.append({"system": system, "sample": sample,
                             "step": step, "time_ms": ms})
        if modes and all(m == "coarse" for m in modes):
            warnings.append(
                f"measure-startup {system}: OVMF port 50/52 markers absent in "
                f"every sample — fell back to {STEP_BOOT_COMBINED} breakdown")
        elif "coarse" in modes:
            n = sum(1 for m in modes if m == "coarse")
            warnings.append(
                f"measure-startup {system}: {n} sample(s) fell back to "
                f"{STEP_BOOT_COMBINED} (no OVMF markers)")
        if no_invoke:
            warnings.append(
                f"measure-startup {system}: {no_invoke} sample(s) lack events "
                f"107/108 — {STEP_RUNTIME}/{STEP_INVOKE} omitted "
                f"(measure_startup.py kills QEMU on systemd init end)")

    # iomgr per-task startup breakdown from measure_vm.py *.mirror files
    iomgr_files = sorted(d.glob("vm_iomgr_*_rep*.mirror"))
    for path in iomgr_files:
        m = re.search(r"_rep(\d+)\.mirror$", path.name)
        sample = int(m.group(1)) if m else -1
        steps = _parse_iomgr_mirror_sample(_read_lines(path))
        if not steps:
            warnings.append(
                f"measure-startup iomgr {path.name}: no STARTUP rows")
            continue
        for step, ms in steps.items():
            rows.append({"system": "iomgr", "sample": sample,
                         "step": step, "time_ms": ms})
    return rows, warnings


# ---------- attestation (Benchmarks/Attestation/results.csv) -----------------

def _attestation_monitor_cold_ms(csv_path):
    """Return (mean_ms, warning_or_None) for measure_monitor_cold."""
    p = Path(csv_path)
    if not p.exists():
        return None, f"attestation: missing {p}"
    try:
        df = pd.read_csv(p)
    except Exception as e:
        return None, f"attestation: failed to read {p}: {e}"
    sel = df[df["Measurement"] == "measure_monitor_cold"]
    if sel.empty:
        return None, f"attestation: 'measure_monitor_cold' not in {p}"
    try:
        return float(sel["Average (ns)"].iloc[0]) / 1e6, None
    except (ValueError, TypeError) as e:
        return None, f"attestation: bad 'measure_monitor_cold' value: {e}"


def _attestation_kernel_mean_ms(csv_path):
    """Return (mean_ms, warning_or_None) for the kernel-hash microbenchmark."""
    p = Path(csv_path)
    if not p.exists():
        return None, f"attestation: missing {p}"
    try:
        df = pd.read_csv(p)
    except Exception as e:
        return None, f"attestation: failed to read {p}: {e}"
    sel = df[df["file"] == "kernel"]["time"]
    if sel.empty:
        return None, f"attestation: no 'kernel' rows in {p}"
    return float(sel.mean()) / 1e6, None


def _parse_attestation(csv_path=ATTESTATION_CSV,
                       breakdown_cvm_csv=ATTESTATION_BREAKDOWN_CVM_CSV):
    """Attach the SVSM Attestation cost to Wallet systems.

    The Attestation step sums:
      - measure_monitor_cold (SNP attestation report for the SVSM Monitor),
        from Benchmarks/Attestation/results.csv
      - kernel-hash time (~61 MB guest kernel image, SHA-via-libmy_crypto),
        averaged over breakdown/cvm/result.csv

    Emitted as a single aggregate row (sample=0) per system in
    WALLET_ATTEST_SYSTEMS, since both inputs are means with different sample
    counts.
    """
    rows, warnings = [], []
    monitor_ms, w = _attestation_monitor_cold_ms(csv_path)
    if w:
        warnings.append(w)
    kernel_ms, w = _attestation_kernel_mean_ms(breakdown_cvm_csv)
    if w:
        warnings.append(w)
    if monitor_ms is None and kernel_ms is None:
        return rows, warnings

    total_ms = (monitor_ms or 0.0) + (kernel_ms or 0.0)
    for system in WALLET_ATTEST_SYSTEMS:
        rows.append({"system": system, "sample": 0,
                     "step": STEP_ATTESTATION, "time_ms": total_ms})
    return rows, warnings


# ---------- public api -------------------------------------------------------

def parse(root: os.PathLike = DEFAULT_ROOT, *, verbose: bool = True,
          measure_startup: os.PathLike = None) -> pd.DataFrame:
    """Return a long-form DataFrame with columns: system, sample, step, time_ms.

    One row per duration sample. Missing/broken inputs produce warnings on
    stderr (when verbose) and are silently dropped from the frame.

    If `measure_startup` is provided, also parse vm/cvm variants of
    pybench/measure_startup.py output (e.g. /tmp/out1/startup_{vm,cvm}_rep*.log).
    Benchmarks/Attestation/results.csv is always read to attach the SVSM
    Attestation cost (monitor cold) to Wallet systems (currently: cvm).
    """
    root = Path(root)
    all_rows, all_warnings = [], []
    for fn in (_parse_native, _parse_gramine, _parse_kata):
        rows, warnings = fn(root)
        all_rows.extend(rows)
        all_warnings.extend(warnings)
    if measure_startup is not None:
        rows, warnings = _parse_measure_startup(measure_startup)
        all_rows.extend(rows)
        all_warnings.extend(warnings)
    rows, warnings = _parse_attestation()
    all_rows.extend(rows)
    all_warnings.extend(warnings)
    if verbose and all_warnings:
        print("[boottime_parser] warnings:", file=sys.stderr)
        for w in all_warnings:
            print(f"  - {w}", file=sys.stderr)
    return pd.DataFrame(all_rows, columns=["system", "sample", "step", "time_ms"])


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measure-startup", metavar="DIR",
                    help="Results dir from pybench/measure_startup.py "
                         "(e.g. /tmp/out1) with startup_{vm,cvm}_rep*.log files")
    ap.add_argument("-o", "--output", metavar="CSV",
                    help="Write the long-form DataFrame to this CSV path")
    args = ap.parse_args()
    df = parse(measure_startup=args.measure_startup)
    print(df)
    if not df.empty:
        print()
        print(df.groupby(["system", "step"])["time_ms"]
                .agg(["count", "mean", "std"]))
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"\nwrote {len(df)} rows to {args.output}", file=sys.stderr)
