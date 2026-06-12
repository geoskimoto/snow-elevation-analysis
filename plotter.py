from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

_PALETTE = [
    '#0072B2', '#E69F00', '#56B4E9', '#009E73',
    '#F0E442', '#D55E00', '#CC79A7', '#000000',
    '#999999', '#117733', '#882255', '#AA4499',
]

_HUC2_BASIN_KEY = 'Columbia River Basin'


def plot_hypsometric(
    bands_by_basin: dict,
    date: datetime,
    output_dir: Path,
) -> list:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = date.strftime('%Y%m%d')
    date_label = date.strftime('%B %d, %Y')
    written = []

    if _HUC2_BASIN_KEY in bands_by_basin:
        df = bands_by_basin[_HUC2_BASIN_KEY]
        fig, ax = plt.subplots(figsize=(8, 10))
        ax.plot(df['mean_swe_mm'], df['elev_band_m'],
                color=_PALETTE[0], linewidth=2)
        ax.set_xlabel('Mean SWE (mm)')
        ax.set_ylabel('Elevation (m)')
        ax.set_title(f'Columbia River Basin\nSWE by Elevation — {date_label}')
        ax.grid(True, alpha=0.3)
        path = output_dir / f'snow_hypsometric_huc2_{date_str}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        written.append(path)

    huc4 = {k: v for k, v in bands_by_basin.items() if k != _HUC2_BASIN_KEY}
    if huc4:
        fig, ax = plt.subplots(figsize=(10, 12))
        for i, (name, df) in enumerate(sorted(huc4.items())):
            ax.plot(df['mean_swe_mm'], df['elev_band_m'],
                    color=_PALETTE[i % len(_PALETTE)],
                    linewidth=1.5, label=name)
        ax.set_xlabel('Mean SWE (mm)')
        ax.set_ylabel('Elevation (m)')
        ax.set_title(f'Columbia River Basin — HUC4 Subbasins\nSWE by Elevation — {date_label}')
        ax.legend(loc='lower right', fontsize=8)
        ax.grid(True, alpha=0.3)
        path = output_dir / f'snow_hypsometric_huc4_{date_str}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        written.append(path)

    return written
