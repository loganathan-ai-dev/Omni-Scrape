"""Universal HTML table and specification grid parser."""

from typing import Any
import lxml.html
from omniscrape.parsers.selector import Element


class TableParser:
    """Parses arbitrary HTML tables and specification grids into dictionaries or lists."""

    @staticmethod
    def parse_table(table_element: Element) -> list[dict[str, str]]:
        """Parses standard rows into list of dictionaries."""
        raw = table_element._node
        headers = []
        rows = []

        # Find headers from thead or first tr
        th_nodes = raw.xpath(".//thead//th | .//tr[1]//th")
        if th_nodes:
            headers = [(th.text_content() or "").strip() for th in th_nodes]

        tr_nodes = raw.xpath(".//tbody//tr | .//tr")
        start_idx = 0
        if not headers and tr_nodes:
            # Use first row as headers
            first_cells = tr_nodes[0].xpath(".//td | .//th")
            headers = [(c.text_content() or "").strip() for c in first_cells]
            start_idx = 1

        for tr in tr_nodes[start_idx:]:
            cells = tr.xpath(".//td | .//th")
            row_vals = [(c.text_content() or "").strip() for c in cells]
            if not row_vals:
                continue

            if headers and len(headers) == len(row_vals):
                rows.append(dict(zip(headers, row_vals)))
            else:
                row_dict = {f"col_{i}": val for i, val in enumerate(row_vals)}
                rows.append(row_dict)

        return rows

    @staticmethod
    def parse_spec_grid(element: Element) -> dict[str, str]:
        """Parses two-column key-value product specification lists."""
        specs = {}
        raw = element._node

        # Pattern 1: standard tr with 2 td
        for tr in raw.xpath(".//tr"):
            cells = tr.xpath(".//td | .//th")
            if len(cells) == 2:
                k = (cells[0].text_content() or "").strip()
                v = (cells[1].text_content() or "").strip()
                if k:
                    specs[k] = v

        # Pattern 2: dl / dt / dd lists
        dts = raw.xpath(".//dt")
        dds = raw.xpath(".//dd")
        if dts and len(dts) == len(dds):
            for dt, dd in zip(dts, dds):
                k = (dt.text_content() or "").strip()
                v = (dd.text_content() or "").strip()
                if k:
                    specs[k] = v

        return specs
