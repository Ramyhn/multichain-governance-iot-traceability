#!/usr/bin/env python3
"""Two-panel partition-recovery figure.

(a) Anchoring staleness over a partition (modeled): the backlog drains in one
    cycle after the link returns.
(b) Measured on the real contract (Foundry): one anchorReconciliation covers
    the whole queued backlog at constant gas, so recovery cost is O(1) in
    partition length.

Usage: python3 plot_partition_validation.py GAS_CSV OUT.pdf
  GAS_CSV columns: backlog_events, anchor_gas
"""
from __future__ import annotations

import csv
import sys

import numpy as np
import matplotlib.pyplot as plt

BLUE, ORANGE, GREEN, RED, GRAY = "#3498db", "#f39c12", "#2ecc71", "#e74c3c", "#7f8c8d"
plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.3,
                     "legend.fontsize": 9.5})


def staleness_series():
    anchor, dt, horizon = 5.0, 0.25, 120.0
    p_start, p_dur = 30.0, 30.0
    healed = p_start + p_dur
    t = np.arange(0.0, horizon + dt, dt)
    s = np.zeros_like(t)
    last = 0.0
    for i, ti in enumerate(t):
        partitioned = p_start <= ti < healed
        if ti - last >= anchor and not partitioned:
            last = ti
        s[i] = ti - last
    return t, s, p_start, healed


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    backlog, gas = [], []
    with open(src) as f:
        for row in csv.reader(f):
            if not row or not row[0].strip().isdigit():
                continue
            backlog.append(int(row[0]))
            gas.append(int(row[1]))
    # steady-state points (drop the one-time cold first anchor at backlog == 1)
    steady = [(b, g) for b, g in zip(backlog, gas) if b >= 100]
    bx = [b for b, _ in steady]
    gy = [g / 1000.0 for _, g in steady]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

    # (a) modeled staleness
    t, s, p0, healed = staleness_series()
    ax1.axvspan(p0, healed, color=RED, alpha=0.10, label="Partition")
    ax1.plot(t, s, color=BLUE, linewidth=2, label="Anchoring staleness")
    ax1.axhline(max(s), color=GRAY, linewidth=1, linestyle=":")
    ax1.set_xlabel("Time (minutes)")
    ax1.set_ylabel("Anchoring staleness (minutes)")
    ax1.set_ylim(0, max(s) * 1.25)
    ax1.set_title("(a) Recovery over a 30-min partition (modeled)")
    ax1.legend(loc="upper right")

    # (b) measured constant anchoring gas
    ax2.semilogx(bx, gy, "o-", color=GREEN, linewidth=2, markersize=7,
                 markeredgecolor="white", markeredgewidth=0.6,
                 label="measured anchor gas")
    ax2.set_xlabel("Backlog cleared by one anchor (events)")
    ax2.set_ylabel("Anchoring gas (thousands)")
    ax2.set_ylim(0, max(gy) * 1.6)
    ax2.set_title("(b) One anchor, any backlog: constant gas (measured)")
    ax2.legend(loc="lower left")

    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print("wrote", out)
    print(f"steady-state gas: {min(g for _, g in steady)}..{max(g for _, g in steady)} "
          f"across backlog {min(bx)}..{max(bx)} events")


if __name__ == "__main__":
    main()
