def test_layout_contains_required_component_ids():
    from layout import get_layout
    layout = get_layout()

    # Convert layout to JSON-serializable dict to check for component IDs
    layout_dict = layout.to_plotly_json()
    layout_str = str(layout_dict)

    required_ids = [
        'date-picker',
        'run-btn',
        'progress-container',
        'progress-bar',
        'progress-label',
        'huc2-graph',
        'huc4-graph',
        'download-section',
        'download-btn',
        'download-data',
        'error-msg',
        'result-store',
        'historical-basin',
        'historical-summary',
        'climatology-graph',
    ]
    for cid in required_ids:
        assert cid in layout_str, f"Component ID '{cid}' missing from layout"


def test_layout_has_historical_tab():
    from layout import get_layout
    layout_str = str(get_layout().to_plotly_json())
    assert "value='historical'" in layout_str
    assert "label='Historical'" in layout_str


def test_dataset_selector_present_with_snodas_default():
    from layout import get_layout

    layout = get_layout()

    def find(component, cid):
        if getattr(component, "id", None) == cid:
            return component
        children = getattr(component, "children", None)
        if children is None:
            return None
        if not isinstance(children, (list, tuple)):
            children = [children]
        for child in children:
            if hasattr(child, "to_plotly_json"):
                found = find(child, cid)
                if found is not None:
                    return found
        return None

    radio = find(layout, "dataset-select")
    assert radio is not None
    assert radio.value == "snodas"
    # SWANN dormant (2026-07-22 HUC6 redesign): options are SNODAS-only while
    # the radio is hidden — see test_dataset_radio_snodas_only_and_hidden.
    assert {o["value"] for o in radio.options} == {"snodas"}

    picker = find(layout, "date-picker")
    assert picker.min_date_allowed is not None

    assert find(layout, "snowpack-footnote") is not None


def _find(component, cid):
    if getattr(component, "id", None) == cid:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            found = _find(child, cid)
            if found is not None:
                return found
    return None


def test_drilldown_selector_and_huc6_graphs_present():
    from layout import get_layout
    layout = get_layout()
    drill = _find(layout, "snowpack-drill")
    assert drill is not None and drill.value == "1706"
    assert len(drill.options) == 12
    assert any("Lower Snake" in o["label"] for o in drill.options)
    for cid in ("huc6-graph", "huc6-volume-graph", "huc6-timeseries-graph"):
        assert _find(layout, cid) is not None, cid


def test_dataset_radio_snodas_only_and_hidden():
    from layout import get_layout
    radio = _find(get_layout(), "dataset-select")
    assert radio is not None and radio.value == "snodas"
    assert [o["value"] for o in radio.options] == ["snodas"]
    assert radio.style.get("display") == "none"


def test_per_tab_drill_selectors_in_their_tabs():
    from layout import get_layout
    layout = get_layout()
    tabs = _find(layout, "main-tabs")
    assert tabs is not None
    assert _find(layout, "huc4-drill") is None            # shared selector removed
    for tab_value, cid in (("snowpack", "snowpack-drill"),
                           ("trends", "trends-drill")):
        tab = next(t for t in tabs.children if t.value == tab_value)
        drill = _find(tab, cid)
        assert drill is not None, cid
        assert drill.value == "1706"
        assert len(drill.options) == 12
