#!/usr/bin/env python3
"""Robustness simulation for the multichain governance architecture (Reviewer 2, W4).

Characterizes behaviour under non-ideal deployment conditions that the paper's
main evaluation does not cover: network partitions between the operational and
analytics chains, validator churn on the operational chain, intermittent device
connectivity at the edge, and partial IPFS availability. Each experiment is a
model grounded in a real mechanism of the architecture:

  E1 partition    -> anchoring is not latency-critical; the daemon queues
                     finalized events and catches up after the partition heals.
  E2 churn        -> GRANDPA finalizes with a >2/3 online supermajority, so
                     liveness degrades gracefully until the 1/3 threshold.
  E3 connectivity -> the edge buffers signed readings; a reading is admitted if
                     it reaches the chain within the timestamp freshness window.
  E4 IPFS         -> content addressing means any replica serves identical
                     bytes, so replication drives retrieval availability.

Results are labelled "simulated" in the paper (distinct from measured and
modelled). Deterministic given the fixed seed.

Usage: python3 robustness_simulation.py [OUTDIR]   (OUTDIR defaults to ./)
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# ---- Paper figure style (matches analysis/generate_paper_tables.py) --------
BLUE, GREEN, ORANGE, RED, PURPLE = "#3498db", "#2ecc71", "#f39c12", "#e74c3c", "#9b59b6"
GRAY = "#7f8c8d"
FIGSIZE = (8, 4.8)
plt.rcParams.update({
    "font.size": 12,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "legend.fontsize": 10.5,
    "axes.grid": True,
    "grid.alpha": 0.3,
})
SEED = 20260709
rng = np.random.default_rng(SEED)


def _save(fig, outdir: Path, name: str) -> None:
    fig.tight_layout()
    fig.savefig(outdir / f"{name}.pdf", dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---- E1: network partition (operational <-> analytics) ---------------------
def exp_partition(outdir: Path) -> dict:
    """Anchoring staleness over time for a partition that blocks anchoring.

    The daemon anchors one Merkle root every ANCHOR_MIN minutes covering all
    events finalized since the last anchor. During a partition it cannot submit,
    so staleness (age of the oldest un-anchored event) grows; on heal the next
    anchor clears the whole backlog. Peak staleness is bounded by D + ANCHOR_MIN
    and no events are lost.
    """
    ANCHOR_MIN = 5.0            # anchoring cadence (minutes)
    EVENT_RATE = 20.0           # finalized events per minute
    horizon = 120.0
    p_start, p_dur = 30.0, 30.0  # partition window (minutes)
    dt = 0.25

    t = np.arange(0.0, horizon + dt, dt)
    staleness = np.zeros_like(t)      # minutes since last successful anchor
    backlog = np.zeros_like(t)        # un-anchored finalized events
    last_anchor = 0.0
    unanchored = 0.0
    peak_stale = 0.0
    recovery_time = None
    healed = p_start + p_dur
    for i, ti in enumerate(t):
        partitioned = p_start <= ti < healed
        # anchor attempts happen on the cadence and succeed only when connected
        if ti - last_anchor >= ANCHOR_MIN and not partitioned:
            last_anchor = ti
            unanchored = 0.0
            if healed <= ti and recovery_time is None:
                recovery_time = ti - healed
        unanchored += EVENT_RATE * dt
        staleness[i] = ti - last_anchor
        backlog[i] = unanchored
        peak_stale = max(peak_stale, staleness[i])

    fig, ax1 = plt.subplots(figsize=FIGSIZE)
    ax1.axvspan(p_start, healed, color=RED, alpha=0.10)
    l_stale, = ax1.plot(t, staleness, color=BLUE, linewidth=2, label="Anchoring staleness")
    ax1.set_xlabel("Time (minutes)")
    ax1.set_ylabel("Anchoring staleness (minutes)", color=BLUE)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(0, peak_stale * 1.25)

    ax2 = ax1.twinx()
    l_back, = ax2.plot(t, backlog, color=ORANGE, linewidth=2, linestyle="--",
                       label="Un-anchored events")
    ax2.set_ylabel("Un-anchored events", color=ORANGE)
    ax2.tick_params(axis="y", labelcolor=ORANGE)
    ax2.grid(False)

    ax1.axhline(peak_stale, color=GRAY, linewidth=1, linestyle=":", label="_nolegend_")
    ax1.annotate(f"peak staleness ≈ {peak_stale:.0f} min",
                 xy=(healed, peak_stale), xytext=(healed + 3, peak_stale * 0.70),
                 color=GRAY, fontsize=10)
    span_proxy = Patch(facecolor=RED, alpha=0.10, label="Partition")
    ax1.legend([span_proxy, l_stale, l_back],
               ["Partition", "Anchoring staleness", "Un-anchored events"],
               loc="upper right")
    ax1.set_title("Anchoring recovery after an operational-to-analytics partition")
    _save(fig, outdir, "robustness_partition")
    return {"partition_min": p_dur, "peak_staleness_min": round(peak_stale, 1),
            "recovery_min": round(recovery_time or 0.0, 2),
            "events_lost": 0}


# ---- E2: validator churn (GRANDPA 2/3 liveness) ----------------------------
def _finalize_prob(n: int, p_off: float) -> float:
    """P(online > 2n/3) with each of n validators independently offline w.p. p_off."""
    need = math.floor(2 * n / 3) + 1
    a = 1.0 - p_off
    return sum(math.comb(n, k) * a**k * p_off**(n - k) for k in range(need, n + 1))


def exp_churn(outdir: Path) -> dict:
    p = np.linspace(0.0, 0.5, 121)
    sets = [(10, GREEN), (31, BLUE), (100, PURPLE)]
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for n, c in sets:
        live = np.array([_finalize_prob(n, pi) for pi in p])
        ax.plot(p * 100, live * 100, color=c, linewidth=2, label=f"N = {n} validators")
    ax.axvline(100 / 3, color=RED, linewidth=1.5, linestyle="--",
               label="1/3 fault threshold")
    ax.set_xlabel("Validator unavailability / churn (%)")
    ax.set_ylabel("Blocks finalized (liveness, %)")
    ax.set_ylim(0, 103)
    ax.set_title("GRANDPA liveness under validator churn")
    ax.legend(loc="lower left")
    # summary: liveness at the 30% churn point for N=31
    live31_30 = _finalize_prob(31, 0.30) * 100
    return {"liveness_pct_at_30pct_churn_N31": round(live31_30, 2),
            "threshold_pct": round(100 / 3, 1)} | _save_ret(fig, outdir, "robustness_churn")


def _save_ret(fig, outdir, name):
    _save(fig, outdir, name)
    return {}


# ---- E3: intermittent device connectivity (freshness window) ---------------
def exp_connectivity(outdir: Path) -> dict:
    """Admitted fraction vs mean outage length, for several freshness windows.

    Alternating on/off connectivity with mean on-time MEAN_ON. A reading emitted
    during an outage is delivered when connectivity returns; with memoryless
    outages the residual wait is Exp(mean_off), so it is admitted (delay <= W)
    with probability 1 - exp(-W/mean_off). Admitted fraction combines readings
    sent while connected (admitted immediately) and while disconnected.
    """
    MEAN_ON = 15.0
    mean_off = np.linspace(0.5, 60.0, 200)
    windows = [(5.0, GREEN), (15.0, BLUE), (60.0, PURPLE)]
    on_frac = MEAN_ON / (MEAN_ON + mean_off)
    off_frac = 1.0 - on_frac
    fig, ax = plt.subplots(figsize=FIGSIZE)
    summary = {}
    for w, c in windows:
        admitted = on_frac + off_frac * (1.0 - np.exp(-w / mean_off))
        ax.plot(mean_off, admitted * 100, color=c, linewidth=2,
                label=f"freshness window = {w:.0f} min")
        # admitted fraction when mean outage equals the freshness window
        idx = int(np.argmin(np.abs(mean_off - w)))
        summary[f"admitted_pct_outage_eq_W{int(w)}"] = round(admitted[idx] * 100, 1)
    ax.set_xlabel("Mean connectivity outage (minutes)")
    ax.set_ylabel("Readings admitted within freshness window (%)")
    ax.set_ylim(0, 103)
    ax.set_title("Edge store-and-forward under intermittent connectivity")
    ax.legend(loc="lower left")
    _save(fig, outdir, "robustness_connectivity")
    return summary


# ---- E4: partial IPFS availability (content-addressed replication) ---------
def exp_ipfs(outdir: Path) -> dict:
    """Retrieval success vs replication factor, for single-event and full-batch.

    A payload is retrievable if at least one of R independent replicas is up;
    with per-replica outage q it is available w.p. 1 - q^R. A single-event proof
    needs one payload; full provenance needs all K events. Content addressing
    means any replica returns identical, hash-checkable bytes.
    """
    K = 1152                    # events in the farm-to-retail batch
    R = np.arange(1, 9)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    summary = {}
    for q, c in [(0.1, BLUE), (0.2, ORANGE)]:
        avail = 1.0 - q**R
        ax.plot(R, avail**1 * 100, color=c, linewidth=2, marker="o", markersize=7,
                linestyle="--", label=f"single event, q = {q}")
        ax.plot(R, avail**K * 100, color=c, linewidth=2, marker="s", markersize=7,
                label=f"full batch (K={K}), q = {q}")
        # smallest R giving >=99% full-batch success
        ok = np.where(avail**K >= 0.99)[0]
        summary[f"min_R_batch99_q{int(q*100)}"] = int(R[ok[0]]) if len(ok) else None
        summary[f"single_event_pct_R3_q{int(q*100)}"] = round((1 - q**3) * 100, 3)
    ax.set_xlabel("Replication factor (independent pins / gateways)")
    ax.set_ylabel("Retrieval success (%)")
    ax.set_ylim(0, 103)
    ax.set_title("Verification retrieval under partial IPFS availability")
    ax.legend(loc="lower right", ncol=2)
    _save(fig, outdir, "robustness_ipfs")
    return summary


def main() -> None:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    outdir.mkdir(parents=True, exist_ok=True)
    stats = {}
    stats.update({f"partition.{k}": v for k, v in exp_partition(outdir).items()})
    stats.update({f"churn.{k}": v for k, v in exp_churn(outdir).items()})
    stats.update({f"connectivity.{k}": v for k, v in exp_connectivity(outdir).items()})
    stats.update({f"ipfs.{k}": v for k, v in exp_ipfs(outdir).items()})

    with open(outdir / "robustness_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in stats.items():
            w.writerow([k, v])

    print(f"Wrote 4 figures + robustness_summary.csv to {outdir}")
    for k, v in stats.items():
        print(f"  {k} = {v}")


if __name__ == "__main__":
    main()
