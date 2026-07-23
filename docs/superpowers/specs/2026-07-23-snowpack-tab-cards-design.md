# Snowpack Tab Section Cards — Design Spec

**Date:** 2026-07-23
**Status:** Approved (conversation), implemented inline same day

## Goal

Visually separate the HUC4 overview from the HUC6 drill-down and put each
drill-down dropdown next to the charts it controls, eliminating the
"disjointed" sidebar dropdown without reintroducing invisible cross-tab
state.

## Design

- Shared card style (white, 6px radius, subtle shadow — matches the HTML
  download page's `.plot` cards).
- **Snowpack tab**: two cards —
  1. "Basin & Subregions (HUC2 · HUC4)": the existing two chart-pair rows,
     unchanged.
  2. "HUC6 Drill-down": header row with the section title left and a
     `snowpack-drill` dropdown right (12 HUC4 options labeled
     `{huc} — {name}`, default `'1706'`, clearable=False); body is the
     existing HUC6 chart pair. Data-source footnote stays below the cards.
- **Trends tab**: the two trend charts stay bare; below them an identical
  "HUC6 Drill-down" card with its own `trends-drill` dropdown (same
  options/default) and the HUC6 trend chart.
- **Sidebar**: the shared `huc4-drill` dropdown is removed entirely.
- **Callbacks**: `update_snowpack_drilldown` input `huc4-drill` →
  `snowpack-drill`; `update_trends_drilldown` input → `trends-drill`.
  No other logic changes. Selections are independent per tab; no syncing.
- Both dropdowns reset to 1706 on page reload (no persistence — YAGNI).

## Testing

Same-commit updates: layout tests assert `huc4-drill` is gone,
`snowpack-drill` lives inside the Snowpack tab, `trends-drill` inside
Trends, both default '1706' with 12 options; callback registration smoke
before commit.
