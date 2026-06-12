import argparse
import sys
from datetime import datetime, date
from pathlib import Path

from basin_loader import load_huc2, load_huc4
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from plotter import plot_hypsometric
from snodas_fetcher import fetch_swe


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate hypsometric SWE curves for the Columbia River Basin."
    )
    parser.add_argument(
        '--date',
        type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
        default=datetime.today().date(),
        help='Date to plot (YYYY-MM-DD). Default: today.',
    )
    parser.add_argument(
        '--band-interval',
        type=int,
        default=250,
        dest='band_interval',
        help='Elevation band interval in metres. Default: 250.',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('output'),
        dest='output_dir',
        help='Directory for output PNGs. Default: output/',
    )
    return parser.parse_args(argv)


def run(dt: datetime, band_interval: int, output_dir: Path) -> None:
    print(f"Fetching SNODAS SWE for {dt.date()}...")
    swe_tif = fetch_swe(dt)

    print("Loading/building aligned DEM...")
    dem_tif = get_aligned_dem(swe_tif)

    print("Loading basin boundaries...")
    huc2 = load_huc2()
    huc4 = load_huc4()

    bands_by_basin = {}

    print("Computing elevation bands for Columbia River Basin (HUC2)...")
    huc2_geom = huc2.geometry[0]
    bands_by_basin['Columbia River Basin'] = compute_bands(
        swe_tif, dem_tif, huc2_geom, band_interval_m=band_interval
    )

    for _, row in huc4.iterrows():
        name = row['name']
        print(f"  Computing bands for {name}...")
        bands_by_basin[name] = compute_bands(
            swe_tif, dem_tif, row.geometry, band_interval_m=band_interval
        )

    print("Generating plots...")
    paths = plot_hypsometric(bands_by_basin, dt, output_dir)
    for p in paths:
        print(f"  Saved: {p}")


def main() -> None:
    args = parse_args()
    dt = datetime.combine(args.date, datetime.min.time())
    try:
        run(dt, band_interval=args.band_interval, output_dir=args.output_dir)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionError as e:
        print(f"Download failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
