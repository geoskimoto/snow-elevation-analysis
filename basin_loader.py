from pathlib import Path

import geopandas as gpd
import pandas as pd

BASEMAP_DIR = Path(__file__).parent / "data" / "basemaps"

# The app brands WBD region 17 ("Pacific Northwest Region") as the Columbia
# River Basin — keep that display name for code '17' only.
_HUC2_DISPLAY_NAME = "Columbia River Basin"


def _load(filename: str) -> gpd.GeoDataFrame:
    path = BASEMAP_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"{filename} not found in {BASEMAP_DIR}")
    return gpd.read_file(path).to_crs(epsg=4326)


def load_huc2() -> gpd.GeoDataFrame:
    return _load("huc2_pnw.geojson")


def load_huc4() -> gpd.GeoDataFrame:
    return _load("huc4_pnw.geojson")


def load_huc6() -> gpd.GeoDataFrame:
    return _load("huc6_pnw.geojson")


def load_all_basins() -> gpd.GeoDataFrame:
    """All 35 basins as rows of (huc, name, geometry), sorted by huc.

    huc is the WBD code string ('17', '1706', '170602') and is the unique
    key used by every parquet, cache, and callback; name is display-only
    (names collide across levels — e.g. Yakima is both 1703 and 170300).
    """
    frames = []
    for gdf, code_col in ((load_huc2(), "huc2"),
                          (load_huc4(), "huc4"),
                          (load_huc6(), "huc6")):
        f = gdf[[code_col, "name", "geometry"]].rename(columns={code_col: "huc"})
        frames.append(f)
    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    out["huc"] = out["huc"].astype(str)
    out.loc[out["huc"] == "17", "name"] = _HUC2_DISPLAY_NAME
    return out.sort_values("huc").reset_index(drop=True)


def transboundary_hucs() -> set[str]:
    """Huc codes whose WBD ``states`` attribute includes Canada ('CN').

    Data-driven from the committed geojsons; used only for display-layer
    daggers — never stored in parquets.
    """
    out = set()
    for gdf, code_col in ((load_huc2(), "huc2"), (load_huc4(), "huc4"),
                          (load_huc6(), "huc6")):
        mask = gdf["states"].fillna("").str.contains("CN")
        out.update(gdf.loc[mask, code_col].astype(str))
    return out


def dagger(name: str, huc: str, tb: set) -> str:
    """Append the transboundary dagger to a display name when flagged."""
    return f"{name} †" if huc in tb else name
