"""One-time fetch of standard WBD basemaps for region 17 from the USGS
WBD ArcGIS REST service. Writes data/basemaps/huc4_pnw.geojson (12
subregions) and data/basemaps/huc6_pnw.geojson (22 basins). Committed for
reproducibility; not part of any scheduled job.

Usage: venv/bin/python scripts/fetch_wbd_basemaps.py
"""
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer"
OUT = Path(__file__).resolve().parent.parent / "data" / "basemaps"
MAX_BYTES = 5_000_000
# (layer id, code field, where clause, output filename, expected count)
LAYERS = [
    (2, "huc4", "huc4 LIKE '17%'", "huc4_pnw.geojson", 12),
    (3, "huc6", "huc6 LIKE '17%'", "huc6_pnw.geojson", 22),
]


def build_query_url(layer: int, field: str, where: str) -> str:
    """Pure helper: builds the ArcGIS REST query URL for a WBD layer.

    maxAllowableOffset=0.001 (~100 m) requests server-side simplification —
    far below the ~1 km SNODAS grid resolution, so it has no effect on
    downstream elevation-band stats while keeping committed geojsons small.
    """
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": f"{field},name,areasqkm,states",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": "0.001",
        "f": "geojson",
    })
    return f"{BASE}/{layer}/query?{params}"


def fetch(layer: int, field: str, where: str) -> bytes:
    url = build_query_url(layer, field, where)
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def main(layers=None) -> None:
    """Fetch each configured layer, validate it, and only then replace the
    committed geojson.

    Writes go to a `.tmp` sibling file first — ALL checks (feature count,
    geometry validity incl. buffer(0) repair, MAX_BYTES size guard) run
    against that temp file. Only once every check passes is it renamed onto
    the committed path. A failed check therefore leaves the previously
    committed file untouched, and the temp file is removed on any exit path
    (success or failure).
    """
    import geopandas as gpd
    if layers is None:
        layers = LAYERS
    for layer, field, where, filename, expected in layers:
        raw = fetch(layer, field, where)
        path = OUT / filename
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(raw)
        try:
            g = gpd.read_file(tmp)
            if len(g) != expected:
                print(f"ERROR: {filename}: got {len(g)} features, expected {expected}",
                      file=sys.stderr)
                sys.exit(1)
            if not g.geometry.is_valid.all():
                g.geometry = g.geometry.buffer(0)
                g.to_file(tmp, driver="GeoJSON")
                if not g.geometry.is_valid.all():
                    print(f"ERROR: {filename}: invalid geometries", file=sys.stderr)
                    sys.exit(1)
            size = tmp.stat().st_size
            if size > MAX_BYTES:
                print(f"ERROR: {filename}: {size} bytes — "
                      f"simplification not applied?", file=sys.stderr)
                sys.exit(1)
            tmp.rename(path)
            print(f"{filename}: {len(g)} features OK")
        finally:
            if tmp.exists():
                tmp.unlink()


if __name__ == "__main__":
    main()
