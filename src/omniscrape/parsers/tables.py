"""Universal HTML table and specification grid parser."""

from omniscrape.parsers.selector import Element


class TableParser:
    """Parses arbitrary HTML tables and specification grids into dictionaries or lists."""

    @staticmethod
    def parse_table(table_element: Element) -> list[dict[str, str]]:
        """Parses standard rows into list of dictionaries."""
        raw = table_element._node
        headers = []
        rows = []

        tr_nodes = list(raw.xpath(".//tbody//tr | .//tr"))
        # De-duplicate (a row inside <tbody> matches both XPath branches) while keeping document order.
        seen: set[int] = set()
        tr_nodes = [tr for tr in tr_nodes if not (id(tr) in seen or seen.add(id(tr)))]

        # Header row: a row inside <thead>, otherwise a first row made of <th> cells. It is consumed as
        # the header and must not also be returned as data.
        header_tr = None
        head_rows = raw.xpath(".//thead//tr")
        if head_rows:
            header_tr = head_rows[0]
        elif tr_nodes and tr_nodes[0].xpath("./th") and not tr_nodes[0].xpath("./td"):
            header_tr = tr_nodes[0]
        if header_tr is not None:
            headers = [(c.text_content() or "").strip() for c in header_tr.xpath("./th | ./td")]
            tr_nodes = [tr for tr in tr_nodes if tr is not header_tr and not tr.xpath("ancestor::thead")]

        start_idx = 0
        if not headers and tr_nodes:
            # No explicit header row: use the first row as headers
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
