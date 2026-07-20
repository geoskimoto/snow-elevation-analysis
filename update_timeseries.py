"""update_timeseries.py — Process today's SWE data.

Intended to be run daily via cron (or systemd timer) to keep the
timeseries current.  Exits cleanly with code 0 if today's band cache
already exists (idempotent / safe to retry).

Usage
-----
    python update_timeseries.py

Exit codes
----------
0   Today processed successfully, or already cached.
1   An error occurred (FTP failure, missing DEM, etc.).
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Load .env before importing config so env-vars are populated when the
# script is run outside the Dash app factory (e.g. via cron or CLI).
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / '.env', override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on env already being set

import config
import datasets
from basin_loader import load_huc2, load_huc4
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from pipeline import load_band_cache, save_band_cache
from timeseries import append_volumes

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HUC2_KEY = 'Columbia River Basin'
_MIN_BAND_AREA_KM2 = 100.0
_LOG_PATH = Path(__file__).parent / 'logs' / 'update_timeseries.log'


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('update_timeseries')
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter('%(asctime)s  %(levelname)-8s  %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    fh = logging.FileHandler(_LOG_PATH)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Process SWE data for a given date (default: today).'
    )
    parser.add_argument(
        '--date',
        type=lambda s: datetime.strptime(s, '%Y-%m-%d'),
        default=None,
        help='Date to process in YYYY-MM-DD format (default: today).'
    )
    parser.add_argument(
        '--dataset',
        choices=('snodas', 'swann', 'both'),
        default='both',
        help='Which dataset(s) to process (default: both).'
    )
    parser.add_argument(
        '--discard-raster',
        action='store_true',
        help='Delete the CONUS SWE GeoTIFF after its bands are computed, so the '
             'daily job does not slowly accumulate intermediate rasters.',
    )
    return parser


def process_dataset(dataset: str, date_arg, cache_dir, huc2, huc4,
                    logger: logging.Logger, discard_raster: bool) -> bool:
    """Fetch and process the latest (or given) date for one dataset.

    Returns True on success or already-current; False on any error (logged).
    """
    ds = datasets.get(dataset)
    dem_cache = cache_dir / 'dem' / ds['dem_filename']
    try:
        # SNODAS/SWANN publish with a lag, so the file for a given day is
        # usually not on the server yet when this runs that morning (a
        # request for today's date returns a fetch error). For the normal
        # cron/default case, fetch the most recent available date instead of
        # failing on today's missing file. An explicit --date still targets
        # that exact day (for backfills).
        if date_arg:
            target = date_arg
            logger.info('[%s] Fetching SWE for %s ...', dataset, target.date())
            swe_tif = ds['fetch_swe'](target, cache_dir=cache_dir)
        else:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            logger.info('[%s] Fetching latest available SWE at or before %s ...',
                        dataset, today.date())
            swe_tif, target = ds['fetch_latest_swe'](today, cache_dir=cache_dir)
            logger.info('[%s] Latest available product: %s', dataset, target.date())

        date_key = target.strftime('%Y%m%d')

        # Idempotency: if bands for the target date are already cached, we're current.
        cached = load_band_cache(date_key, cache_dir, dataset)
        if cached is not None:
            logger.info('[%s] Band cache already exists for %s — nothing to do.',
                        dataset, target.date())
            try:
                append_volumes(target, cached, cache_dir, dataset=dataset)
            except Exception as exc:
                logger.warning('[%s] timeseries append failed (non-fatal): %s',
                               dataset, exc)
            return True

        logger.info('[%s] Loading aligned DEM ...', dataset)
        dem_tif = get_aligned_dem(swe_tif, dem_cache=dem_cache)

        logger.info('[%s] Computing elevation bands ...', dataset)
        bands_by_basin: dict = {
            _HUC2_KEY: compute_bands(swe_tif, dem_tif, huc2.geometry[0],
                                     min_band_area_km2=_MIN_BAND_AREA_KM2)
        }
        for _, row in huc4.iterrows():
            bands_by_basin[row['name']] = compute_bands(
                swe_tif, dem_tif, row.geometry,
                min_band_area_km2=_MIN_BAND_AREA_KM2)

        save_band_cache(bands_by_basin, date_key, cache_dir, dataset)
        append_volumes(target, bands_by_basin, cache_dir, dataset=dataset)
        if discard_raster:
            swe_tif.unlink(missing_ok=True)
            logger.debug('[%s] Discarded raster %s', dataset, swe_tif.name)

        logger.info('[%s] Done — %d basins processed for %s.',
                    dataset, len(bands_by_basin), target.date())
        return True

    except (ConnectionError, OSError, IOError) as exc:
        logger.error('[%s] Fetch / network error: %s', dataset, exc)
        return False
    except Exception as exc:
        logger.error('[%s] Unexpected error: %s', dataset, exc, exc_info=True)
        return False


def main() -> None:
    args = build_parser().parse_args()
    logger = _setup_logging()
    cache_dir = config.get_cache_dir()
    date_arg = (args.date.replace(hour=0, minute=0, second=0, microsecond=0)
                if args.date else None)

    logger.info('=== update_timeseries (datasets: %s) ===', args.dataset)
    logger.info('cache_dir: %s', cache_dir)

    logger.info('Loading basin boundaries ...')
    huc2 = load_huc2()
    huc4 = load_huc4()

    targets = ('snodas', 'swann') if args.dataset == 'both' else (args.dataset,)
    results = {
        d: process_dataset(d, date_arg, cache_dir, huc2, huc4, logger,
                           discard_raster=args.discard_raster)
        for d in targets
    }
    failed = [d for d, ok in results.items() if not ok]
    if failed:
        logger.error('Datasets failed: %s', ', '.join(failed))
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
