"""populate_timeseries.py — Backfill SWE elevation-band data.

Processes every date from Oct 1, 2025 through yesterday (inclusive).
Skips dates whose band-cache parquet already exists.
Logs progress to logs/populate_timeseries.log and to stdout.
FTP / download errors for individual dates are caught and logged; the
script then continues with the next date rather than aborting.

Usage
-----
    python populate_timeseries.py [--start YYYY-MM-DD] [--discard-raster]

Options
-------
--start YYYY-MM-DD   Override the default start date of 2025-10-01.
                     Useful for resuming a partial run.
--discard-raster     Delete each CONUS SWE GeoTIFF once its bands are computed.
                     Recommended for the full-record backfill so the run does
                     not accumulate ~65 GB of intermediate rasters; the volume
                     parquet the climatology/trends tabs need is unaffected.

Exit codes
----------
0   All dates processed (or already cached).
1   One or more dates failed; see the log for details.
"""

import argparse
import logging
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Load .env before importing config so env-vars are populated when the
# script is run outside the Dash app factory (e.g. via cron or CLI).
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / '.env', override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on env already being set

import rasterio

import config
import datasets
import swann_fetcher
from basin_loader import load_huc2, load_huc4
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from pipeline import load_band_cache, save_band_cache
from snodas_fetcher import fetch_swe
from timeseries import append_volumes, load_timeseries, water_year

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HUC2_KEY = 'Columbia River Basin'
_DEFAULT_START = date(2025, 10, 1)
_MIN_BAND_AREA_KM2 = 100.0
_LOG_PATH = Path(__file__).parent / 'logs' / 'populate_timeseries.log'


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('populate_timeseries')
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter('%(asctime)s  %(levelname)-8s  %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # File handler — full DEBUG detail
    fh = logging.FileHandler(_LOG_PATH)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--start', metavar='YYYY-MM-DD',
                        default=_DEFAULT_START.isoformat(),
                        help='First date to process (default: 2025-10-01)')
    parser.add_argument('--dataset', choices=('snodas', 'swann'), default='snodas',
                        help='Dataset to backfill (default: snodas). SWANN uses '
                             'bulk water-year files (WY1982-WY2023) and falls back '
                             'to daily files for later years.')
    parser.add_argument('--discard-raster', action='store_true',
                        help='Delete each downloaded raster/netCDF after processing.')
    return parser


# ---------------------------------------------------------------------------
# SWANN time-value parsing
# ---------------------------------------------------------------------------

_TIME_UNITS_RE = re.compile(r'^days since (\d{4}-\d{2}-\d{2})')


def parse_time_values(tags: dict) -> list[datetime]:
    """Decode GDAL netCDF global tags into one datetime per time band.

    SWANN WY files carry time as 'days since 1900-01-01'; anything else is a
    format change we must not silently misread.
    """
    m = _TIME_UNITS_RE.match(tags.get('time#units', ''))
    if not m:
        raise ValueError(
            f"Unexpected SWANN time units: {tags.get('time#units')!r}")
    origin = datetime.strptime(m.group(1), '%Y-%m-%d')
    raw = tags['NETCDF_DIM_time_VALUES'].strip('{}')
    return [origin + timedelta(days=int(float(v))) for v in raw.split(',')]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _process_date(
    target: date,
    cache_dir: Path,
    dem_cache: Path,
    huc2,
    huc4,
    logger: logging.Logger,
    discard_raster: bool = False,
) -> bool:
    """Process a single date.  Returns True on success, False on failure.

    When *discard_raster* is set, the cached CONUS SWE GeoTIFF is deleted once
    its elevation bands have been computed.  The climatology/trends features
    only need the (tiny) volume parquet, so this keeps the full-record backfill
    from parking ~65 GB of intermediate rasters on disk.
    """
    date_key = target.strftime('%Y%m%d')
    dt = datetime(target.year, target.month, target.day)

    # Skip if band cache already present (also covers timeseries idempotency)
    cached = load_band_cache(date_key, cache_dir)
    if cached is not None:
        logger.info('%s  SKIP  band cache exists', target)
        # Still append to timeseries in case that step was missed previously
        try:
            append_volumes(dt, cached, cache_dir)
        except Exception as exc:
            logger.warning('%s  timeseries append failed (skipped): %s', target, exc)
        return True

    try:
        logger.info('%s  fetching SNODAS SWE ...', target)
        swe_tif = fetch_swe(dt, cache_dir=cache_dir)

        logger.debug('%s  loading aligned DEM ...', target)
        dem_tif = get_aligned_dem(swe_tif, dem_cache=dem_cache)

        logger.debug('%s  computing elevation bands ...', target)
        bands_by_basin: dict = {
            _HUC2_KEY: compute_bands(
                swe_tif, dem_tif, huc2.geometry[0],
                min_band_area_km2=_MIN_BAND_AREA_KM2,
            )
        }
        for _, row in huc4.iterrows():
            bands_by_basin[row['name']] = compute_bands(
                swe_tif, dem_tif, row.geometry,
                min_band_area_km2=_MIN_BAND_AREA_KM2,
            )

        save_band_cache(bands_by_basin, date_key, cache_dir)
        append_volumes(dt, bands_by_basin, cache_dir)
        if discard_raster:
            swe_tif.unlink(missing_ok=True)
            logger.debug('%s  discarded raster %s', target, swe_tif.name)
        logger.info('%s  OK  (%d basins)', target, len(bands_by_basin))
        return True

    except (ConnectionError, OSError, IOError) as exc:
        # FTP / network errors — log and continue backfill
        logger.error('%s  FETCH ERROR: %s', target, exc)
        return False
    except Exception as exc:
        logger.error('%s  ERROR: %s', target, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# SWANN backfill
# ---------------------------------------------------------------------------

def _swann_dates_done(wy: int, cache_dir: Path, n_basins: int) -> set:
    """Dates already fully recorded (all basins) in the SWANN WY parquet."""
    df = load_timeseries(wy, cache_dir, dataset='swann')
    if df.empty:
        return set()
    counts = df.groupby('date')['basin'].nunique()
    return {ts.to_pydatetime().date() for ts, n in counts.items() if n >= n_basins}


def _swann_process_day(swe_tif: Path, dem_tif: Path, dt: datetime,
                       huc2, huc4, cache_dir: Path) -> None:
    """Compute per-basin bands in memory and append volumes (no band cache —
    the full-record backfill only needs the tiny volume parquets; band caches
    build on demand from the Snowpack tab, per the design spec)."""
    bands_by_basin: dict = {
        _HUC2_KEY: compute_bands(swe_tif, dem_tif, huc2.geometry[0],
                                 min_band_area_km2=_MIN_BAND_AREA_KM2)
    }
    for _, row in huc4.iterrows():
        bands_by_basin[row['name']] = compute_bands(
            swe_tif, dem_tif, row.geometry, min_band_area_km2=_MIN_BAND_AREA_KM2)
    append_volumes(dt, bands_by_basin, cache_dir, dataset='swann')


def _run_swann_backfill(start: date, end: date, cache_dir: Path,
                        huc2, huc4, logger: logging.Logger,
                        discard: bool) -> list[date]:
    """Backfill SWANN volumes for [start, end]. Returns failed dates."""
    ds = datasets.get('swann')
    dem_cache = cache_dir / 'dem' / ds['dem_filename']
    n_basins = 1 + len(huc4)
    failed: list[date] = []
    tmp_tif = cache_dir / 'swann' / 'wy_extract_tmp.tif'

    first_wy = water_year(datetime(start.year, start.month, start.day))
    last_wy = water_year(datetime(end.year, end.month, end.day))

    for wy in range(first_wy, last_wy + 1):
        done = _swann_dates_done(wy, cache_dir, n_basins)
        try:
            wy_nc = swann_fetcher.download_wy_nc(wy, cache_dir / 'swann')
        except FileNotFoundError:
            wy_nc = None       # no bulk file (WY2024+): daily-file mode
        except ConnectionError as exc:
            logger.error('WY%d  bulk download failed: %s — skipping year', wy, exc)
            wy_start = date(wy - 1, 10, 1)
            failed.extend([wy_start])   # marker; details in log
            continue

        if wy_nc is not None:
            logger.info('WY%d  bulk file mode (%s)', wy, wy_nc.name)
            sd = f'netcdf:{wy_nc}:SWE'
            with rasterio.open(sd) as src:
                band_dates = parse_time_values(src.tags())
                n_bands = src.count
            if len(band_dates) != n_bands:
                logger.error('WY%d  time axis mismatch (%d dates, %d bands) — skipping',
                             wy, len(band_dates), n_bands)
                failed.append(date(wy - 1, 10, 1))
                continue
            for band_idx, dt in enumerate(band_dates, start=1):
                d = dt.date()
                if d < start or d > end or d in done:
                    continue
                try:
                    swann_fetcher.nc_to_geotiff(wy_nc, tmp_tif, variable='SWE',
                                                band=band_idx)
                    dem_tif = get_aligned_dem(tmp_tif, dem_cache=dem_cache)
                    _swann_process_day(tmp_tif, dem_tif, dt, huc2, huc4, cache_dir)
                    logger.info('%s  OK (WY file band %d)', d, band_idx)
                except Exception as exc:
                    logger.error('%s  ERROR: %s', d, exc)
                    failed.append(d)
            tmp_tif.unlink(missing_ok=True)
            if discard:
                wy_nc.unlink(missing_ok=True)
                logger.debug('WY%d  discarded %s', wy, wy_nc.name)
        else:
            logger.info('WY%d  daily file mode (no bulk file)', wy)
            d = max(start, date(wy - 1, 10, 1))
            wy_end = min(end, date(wy, 9, 30))
            while d <= wy_end:
                if d not in done:
                    dt = datetime(d.year, d.month, d.day)
                    try:
                        swe_tif = swann_fetcher.fetch_swe(dt, cache_dir=cache_dir)
                        dem_tif = get_aligned_dem(swe_tif, dem_cache=dem_cache)
                        _swann_process_day(swe_tif, dem_tif, dt, huc2, huc4, cache_dir)
                        if discard:
                            swe_tif.unlink(missing_ok=True)
                        logger.info('%s  OK (daily file)', d)
                    except Exception as exc:
                        logger.error('%s  ERROR: %s', d, exc)
                        failed.append(d)
                d += timedelta(days=1)
    return failed


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.dataset == 'swann' and args.start == _DEFAULT_START.isoformat():
            start = date(1981, 10, 1)
        else:
            start = date.fromisoformat(args.start)
    except ValueError:
        print(f'ERROR: invalid --start date "{args.start}"; use YYYY-MM-DD', file=sys.stderr)
        sys.exit(1)

    yesterday = date.today() - timedelta(days=1)
    if start > yesterday:
        print(f'Start date {start} is after yesterday ({yesterday}); nothing to do.')
        sys.exit(0)

    logger = _setup_logging()

    cache_dir = config.get_cache_dir()
    dem_cache = cache_dir / 'dem' / 'columbia_basin_swe_aligned.tif'

    logger.info('=== populate_timeseries START ===')
    logger.info('date range: %s → %s', start, yesterday)
    logger.info('cache_dir : %s', cache_dir)

    logger.info('Loading basin boundaries ...')
    huc2 = load_huc2()
    huc4 = load_huc4()

    if args.dataset == 'swann':
        failed = _run_swann_backfill(start, yesterday, cache_dir, huc2, huc4,
                                     logger, discard=args.discard_raster)
        logger.info('=== populate_timeseries (swann) DONE — %d failures ===',
                    len(failed))
        if failed:
            logger.warning('Failed dates: %s', ', '.join(str(d) for d in failed))
            sys.exit(1)
        sys.exit(0)

    total_dates = (yesterday - start).days + 1
    failed: list[date] = []

    current = start
    idx = 0
    while current <= yesterday:
        idx += 1
        logger.debug('--- [%d/%d] %s ---', idx, total_dates, current)
        ok = _process_date(current, cache_dir, dem_cache, huc2, huc4, logger,
                           discard_raster=args.discard_raster)
        if not ok:
            failed.append(current)
        current += timedelta(days=1)

    logger.info('=== populate_timeseries DONE ===')
    logger.info('Processed %d dates; %d failed', total_dates, len(failed))
    if failed:
        logger.warning('Failed dates: %s', ', '.join(str(d) for d in failed))
        sys.exit(1)


if __name__ == '__main__':
    main()
