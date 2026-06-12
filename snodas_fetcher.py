import ftplib
import gzip
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

SNODAS_FTP_HOST = "sidads.colorado.edu"
SNODAS_ROWS = 3351
SNODAS_COLS = 6935
SNODAS_XMIN = -124.733749999
SNODAS_YMAX = 52.874583333
SNODAS_CELLSIZE = 0.00833333333
SNODAS_NODATA = -9999

_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

_DEFAULT_CACHE = Path(__file__).parent / "data" / "cache" / "snodas"
_SNODAS_START = datetime(2003, 10, 1)


def validate_date(date: datetime) -> None:
    if date < _SNODAS_START:
        raise ValueError(
            f"SNODAS begins October 2003; requested date {date.date()} is too early."
        )


def ftp_dir_path(date: datetime) -> str:
    return (
        f"/pub/DATASETS/NOAA/G02158/masked/"
        f"{date.year}/{date.month:02d}_{_MONTH_ABBR[date.month]}/"
    )


def ftp_filename(date: datetime) -> str:
    return f"SNODAS_{date.strftime('%Y%m%d')}.tar"


def swe_dat_filename(date: datetime) -> str:
    return f"us_ssmv11034tS__T0001TTNATS{date.strftime('%Y%m%d')}05HP001.dat.gz"


def cache_path(date: datetime, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    return cache_dir / f"{date.year}" / f"{date.month:02d}" / f"{date.strftime('%Y%m%d')}_swe.tif"


def dat_to_geotiff(
    dat_path: Path,
    tif_path: Path,
    rows: int = SNODAS_ROWS,
    cols: int = SNODAS_COLS,
) -> None:
    data = np.fromfile(dat_path, dtype=">i2").reshape(rows, cols)
    transform = from_origin(SNODAS_XMIN, SNODAS_YMAX, SNODAS_CELLSIZE, SNODAS_CELLSIZE)
    tif_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        tif_path, "w",
        driver="GTiff",
        height=rows, width=cols,
        count=1, dtype="int16",
        crs="EPSG:4326",
        transform=transform,
        nodata=SNODAS_NODATA,
        compress="lzw",
    ) as dst:
        dst.write(data, 1)


def download_and_extract(date: datetime, tif_path: Path) -> None:
    tmp_tar = tif_path.parent / ftp_filename(date)
    tif_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with ftplib.FTP(SNODAS_FTP_HOST) as ftp:
            ftp.login()
            ftp.cwd(ftp_dir_path(date))
            with open(tmp_tar, "wb") as f:
                ftp.retrbinary(f"RETR {ftp_filename(date)}", f.write)
    except ftplib.all_errors as e:
        if tmp_tar.exists():
            tmp_tar.unlink()
        raise ConnectionError(
            f"SNODAS FTP download failed for {date.date()}: {e}\n"
            f"Try an earlier date or check your connection."
        ) from e

    dat_gz_name = swe_dat_filename(date)
    tmp_dat_gz = tif_path.parent / dat_gz_name
    tmp_dat = tif_path.parent / dat_gz_name.replace(".gz", "")

    try:
        with tarfile.open(tmp_tar) as tar:
            try:
                member = tar.getmember(dat_gz_name)
            except KeyError:
                raise RuntimeError(
                    f"Expected SWE file '{dat_gz_name}' not found in SNODAS archive "
                    f"for {date.date()}. The SNODAS filename format may have changed."
                )
            with tar.extractfile(member) as gz_file, open(tmp_dat_gz, "wb") as out:
                out.write(gz_file.read())
        with gzip.open(tmp_dat_gz, "rb") as gz, open(tmp_dat, "wb") as out:
            shutil.copyfileobj(gz, out)
        dat_to_geotiff(tmp_dat, tif_path)
    except Exception:
        if tif_path.exists():
            tif_path.unlink()
        raise
    finally:
        for p in [tmp_tar, tmp_dat_gz, tmp_dat]:
            if p.exists():
                p.unlink()


def fetch_swe(date: datetime, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    validate_date(date)
    tif = cache_path(date, cache_dir)
    if tif.exists():
        return tif
    download_and_extract(date, tif)
    return tif
