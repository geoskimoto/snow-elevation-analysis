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
from basin_loader import load_huc2, load_huc4
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from pipeline import load_band_cache, save_band_cache
from snodas_fetcher import fetch_swe
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

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Process SWE data for a given date (default: today).'
    )
    parser.add_argument(
        '--date',
        type=lambda s: datetime.strptime(s, '%Y-%m-%d'),
        default=None,
        help='Date to process in YYYY-MM-DD format (default: today).'
    )
    args = parser.parse_args()

    logger = _setup_logging()
    if args.date:
        today = args.date.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    date_key = today.strftime('%Y%m%d')

    cache_dir = config.get_cache_dir()
    dem_cache = cache_dir / 'dem' / 'columbia_basin_swe_aligned.tif'

    logger.info('=== update_timeseries %s ===', today.date())
    logger.info('cache_dir: %s', cache_dir)

    # Load basin boundaries early (outside try block) so missing files fail loudly
    logger.info('Loading basin boundaries ...')
    huc2 = load_huc2()
    huc4 = load_huc4()

    # Idempotency: exit cleanly if band cache already present
    cached = load_band_cache(date_key, cache_dir)
    if cached is not None:
        logger.info('Band cache already exists for %s — nothing to do.', today.date())
        # Ensure timeseries entry exists in case it was missed in a prior run
        try:
            append_volumes(today, cached, cache_dir)
        except Exception as exc:
            logger.warning('timeseries append failed (non-fatal): %s', exc)
        sys.exit(0)

    try:
        logger.info('Fetching SNODAS SWE for %s ...', today.date())
        swe_tif = fetch_swe(today, cache_dir=cache_dir)

        logger.info('Loading aligned DEM ...')
        dem_tif = get_aligned_dem(swe_tif, dem_cache=dem_cache)

        logger.info('Computing elevation bands ...')
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
        append_volumes(today, bands_by_basin, cache_dir)

        logger.info('Done — %d basins processed for %s.', len(bands_by_basin), today.date())
        sys.exit(0)

    except (ConnectionError, OSError, IOError) as exc:
        logger.error('FTP / network error: %s', exc)
        sys.exit(1)
    except Exception as exc:
        logger.error('Unexpected error: %s', exc, exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
