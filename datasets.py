"""datasets.py — registry of gridded SWE datasets the app can analyze.

Single source of truth for dataset routing: labels, record start, fetcher
functions, and DEM cache filename. Cache-subtree routing itself lives in
timeseries/climatology/pipeline via the convention "non-'snodas' datasets
use a subdir named after the dataset key" — those modules deliberately do
not import this one (swann_fetcher imports timeseries, so an import here
would cycle).
"""

from datetime import datetime

import snodas_fetcher
import swann_fetcher

DATASETS = {
    "snodas": {
        "label": "SNODAS (~1 km)",
        "start": datetime(2003, 10, 1),
        "dem_filename": "columbia_basin_swe_aligned.tif",
        "fetch_swe": snodas_fetcher.fetch_swe,
        "fetch_latest_swe": snodas_fetcher.fetch_latest_swe,
        "footnote": (
            "NOAA SNODAS (~1 km daily gridded SWE, WY2004-present). Assimilates "
            "SNOTEL/COOP ground stations with meteorological model forcing. "
            "Limitations: Station network thins above ~7,000 ft, leading to "
            "underestimation of deep mountain snowpack (published bias: 20-40% low "
            "in high-elevation basins). Glacier pixels are excluded."
        ),
    },
    "swann": {
        "label": "SWANN (4 km)",
        "start": datetime(1981, 10, 1),
        "dem_filename": "columbia_basin_swann_aligned.tif",
        "fetch_swe": swann_fetcher.fetch_swe,
        "fetch_latest_swe": swann_fetcher.fetch_latest_swe,
        "footnote": (
            "UA SWANN / UA-SWE (4 km daily gridded SWE, WY1982-present). "
            "Interpolates SNOTEL and COOP observations using PRISM "
            "temperature/precipitation gradients. Limitations: 4 km pixels span "
            "wide elevation ranges in steep terrain, so per-elevation-band SWE is "
            "smeared and hypsometric curves are coarser than SNODAS (~1 km)."
        ),
    },
}


def get(dataset: str) -> dict:
    if dataset not in DATASETS:
        raise KeyError(
            f"Unknown dataset '{dataset}'; expected one of {sorted(DATASETS)}")
    return DATASETS[dataset]
