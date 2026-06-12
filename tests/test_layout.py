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
    ]
    for cid in required_ids:
        assert cid in layout_str, f"Component ID '{cid}' missing from layout"
