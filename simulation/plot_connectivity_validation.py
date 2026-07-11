#!/usr/bin/env python3
"""Plot measured (pallet) connectivity admission against the analytical model.

Reads the measured CSV produced by the pallet test connectivity_measurement
(columns: mean_outage_min, window_min, admitted_pct) and overlays those points
on the same store-and-forward model used by the simulation, one curve per
freshness window. Shows that the real admission path matches the model.

Usage: python3 plot_connectivity_validation.py MEASURED.csv OUT.pdf
"""
from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt

GREEN, BLUE, PURPLE = "#2ecc71", "#3498db", "#9b59b6"
COLOR = {5: GREEN, 15: BLUE, 60: PURPLE}
MEAN_ON = 15.0  # minutes, matches the measurement
FIGSIZE = (8, 4.8)
plt.rcParams.update({"font.size": 12, "axes.grid": True, "grid.alpha": 0.3,
                     "legend.fontsize": 10})


def model(off_min: np.ndarray, w_min: float) -> np.ndarray:
    on = MEAN_ON / (MEAN_ON + off_min)
    return (on + (1.0 - on) * (1.0 - np.exp(-w_min / off_min))) * 100.0


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    measured = defaultdict(list)  # window_min -> list[(off_min, pct)]
    with open(src) as f:
        for row in csv.reader(f):
            if not row or row[0].strip() in ("mean_outage_min", ""):
                continue
            off, w, pct = float(row[0]), int(float(row[1])), float(row[2])
            measured[w].append((off, pct))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    off_line = np.linspace(1.0, 60.0, 300)
    for w in sorted(measured):
        c = COLOR.get(w, "#333333")
        ax.plot(off_line, model(off_line, w), color=c, linewidth=2,
                label=f"model, window = {w} min")
        pts = sorted(measured[w])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, "o", color=c, markersize=6, markeredgecolor="white",
                markeredgewidth=0.6, label=f"measured, window = {w} min")

    ax.set_xlabel("Mean connectivity outage (minutes)")
    ax.set_ylabel("Readings admitted within freshness window (%)")
    ax.set_ylim(0, 103)
    # no title; the figure caption describes the plot
    ax.legend(loc="lower left", ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print("wrote", out)

    # report max deviation between measured and model
    worst = 0.0
    for w, pts in measured.items():
        for off, pct in pts:
            worst = max(worst, abs(pct - float(model(np.array([off]), w)[0])))
    print(f"max |measured - model| = {worst:.2f} percentage points")


if __name__ == "__main__":
    main()
