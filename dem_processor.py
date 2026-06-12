from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling

_DEFAULT_DEM_CACHE = (
    Path(__file__).parent / "data" / "cache" / "dem" / "columbia_basin_swe_aligned.tif"
)
_COLUMBIA_BASIN_BOUNDS = (-125.0, 42.0, -110.0, 52.0)


def warp_dem_to_grid(raw_dem: Path, reference_tif: Path, output: Path) -> None:
    """Reproject and resample raw_dem to exactly match reference_tif grid."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(reference_tif) as ref:
        dst_crs = ref.crs
        dst_transform = ref.transform
        dst_width = ref.width
        dst_height = ref.height

    with rasterio.open(raw_dem) as src:
        data, _ = rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=np.empty((dst_height, dst_width), dtype=np.float32),
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
            dst_nodata=-9999.0,
        )

    with rasterio.open(
        output, "w",
        driver="GTiff",
        height=dst_height, width=dst_width,
        count=1, dtype="float32",
        crs=dst_crs,
        transform=dst_transform,
        nodata=-9999.0,
        compress="lzw",
    ) as dst:
        dst.write(data, 1)


def build_aligned_dem(swe_tif: Path, dem_cache: Path) -> None:
    """Fetch SRTM 90m for Columbia Basin bbox, warp to SNODAS grid, cache."""
    import elevation

    dem_cache.parent.mkdir(parents=True, exist_ok=True)
    tmp_raw = dem_cache.parent / "raw_dem_download.tif"
    tmp_warped = dem_cache.parent / "dem_warped.tmp.tif"

    try:
        elevation.clip(
            bounds=_COLUMBIA_BASIN_BOUNDS,
            output=str(tmp_raw),
            product="SRTM3",
        )
        warp_dem_to_grid(tmp_raw, swe_tif, tmp_warped)
        tmp_warped.rename(dem_cache)
    finally:
        for p in [tmp_raw, tmp_warped]:
            if p.exists():
                p.unlink()
        elevation.clean()


def get_aligned_dem(
    swe_tif: Path,
    dem_cache: Path = _DEFAULT_DEM_CACHE,
) -> Path:
    if dem_cache.exists():
        return dem_cache
    build_aligned_dem(swe_tif, dem_cache)
    return dem_cache
