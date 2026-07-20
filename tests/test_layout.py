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
    assert {o["value"] for o in radio.options} == {"snodas", "swann"}

    picker = find(layout, "date-picker")
    assert picker.min_date_allowed is not None

    assert find(layout, "snowpack-footnote") is not None
