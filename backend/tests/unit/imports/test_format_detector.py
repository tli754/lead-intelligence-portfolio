from app.modules.imports.domain.format_detector import detect_storeleads_format


class TestDetectStoreleadsFormat:
    def test_vaadin_grid_marker_present(self) -> None:
        html = (
            '<vaadin-grid-cell-content slot="vaadin-grid-cell-content-0">'
            "</vaadin-grid-cell-content>"
        )
        assert detect_storeleads_format(html) == "vaadin_grid"

    def test_plain_table_markup_is_table(self) -> None:
        html = "<table><tr><th>Website</th></tr><tr><td>example.com</td></tr></table>"
        assert detect_storeleads_format(html) == "table"

    def test_empty_string_is_table(self) -> None:
        assert detect_storeleads_format("") == "table"

    def test_garbage_input_is_table(self) -> None:
        assert detect_storeleads_format("not html at all, just some text") == "table"

    def test_mixed_input_with_both_table_and_vaadin_marker_prefers_vaadin_grid(self) -> None:
        html = (
            "<table><tr><td>example.com</td></tr></table>"
            '<vaadin-grid-cell-content slot="vaadin-grid-cell-content-0">'
            "</vaadin-grid-cell-content>"
        )
        assert detect_storeleads_format(html) == "vaadin_grid"
