import hashlib
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from vn_traffic_risk.core.config import PROJECT_ROOT, read_yaml


def test_catalog_faithfully_preserves_all_workbook_rows():
    source = PROJECT_ROOT/"docs/sources/single-risk_Interaction.xlsx"
    provenance = read_yaml(PROJECT_ROOT/"docs/sources/provenance.yaml")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == provenance["sha256"]
    ns = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(source) as book:
        strings = ["".join(t.text or "" for t in row.findall(".//s:t",ns))
                   for row in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("s:si",ns)]
        rows = ET.fromstring(book.read("xl/worksheets/sheet1.xml")).findall("s:sheetData/s:row",ns)
        found = {}
        for row in rows:
            cells = {}
            for cell in row.findall("s:c",ns):
                value = cell.find("s:v",ns)
                if value is not None:
                    cells[cell.attrib["r"].rstrip("0123456789")] = strings[int(value.text)] if cell.attrib.get("t")=="s" else value.text
            if cells.get("A","").startswith("INT-"):
                found[cells["A"]] = cells
    catalog = read_yaml(PROJECT_ROOT/"configs/catalog.yaml")["scenarios"]
    assert len(found) == len(catalog) == 20
    for scenario in catalog:
        row = found[scenario["id"]]
        assert (scenario["name"], scenario["risk"], scenario["counterfactual"]) == (row["B"],row["C"],row["D"])
