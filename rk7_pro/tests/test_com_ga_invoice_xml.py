import unittest
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
from rk7_pro.core.udb_checkview_service import UdbCheckViewService


ROOT = Path(__file__).resolve().parents[2]


class ComGaInvoiceXmlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        service = UdbCheckViewService()
        cls.db = service.parse_udb_database(ROOT / "sh00329.udb")
        cls.master = service.ref_service.get_master_data_for_restaurant("1010763")
        source = (ROOT / "invoice.xml").read_text(encoding="utf-8-sig")
        cls.reference = ET.fromstring("<ROOT>" + source + "</ROOT>")

    def test_cash_discount_and_combo_receipts_match_pos_sample(self):
        for number in ("1164333", "1164384", "1164402"):
            with self.subTest(check=number):
                raw = next(row for row in self.db["_raw_tables"]["PRINTCHECKS"]
                           if row.get("CHECKNUM") == number and row.get("STATE") == "6")
                actual = ET.fromstring(InvoiceXmlTemplateService.build(
                    self.db, self.master, raw["VISIT"], raw["UNI"]))
                expected = next(receipt for receipt in self.reference.findall("RECEIPT")
                                if (line := receipt.find("./CHECKDATA/CHECK/LINE")) is not None
                                and line.get("CheckNum") == number)
                for section in ("CHECK", "DISHES", "TAXES", "DISCOUNT", "PAYMENT"):
                    actual_lines = actual.findall(f"./CHECKDATA/{section}/LINE")
                    expected_lines = expected.findall(f"./CHECKDATA/{section}/LINE")
                    self.assertEqual(len(actual_lines), len(expected_lines), section)
                    for actual_line, expected_line in zip(actual_lines, expected_lines):
                        normalized = lambda attrs: {key: unicodedata.normalize("NFC", value)
                                                    for key, value in attrs.items()}
                        self.assertEqual(normalized(actual_line.attrib),
                                         normalized(expected_line.attrib))

    def test_all_closed_checks_export_and_reconcile(self):
        closed = [row for row in self.db["_raw_tables"]["PRINTCHECKS"]
                  if row.get("STATE") == "6"]
        self.assertEqual(len(closed), 517)
        for row in closed:
            with self.subTest(check=row.get("CHECKNUM")):
                root = ET.fromstring(InvoiceXmlTemplateService.build(
                    self.db, self.master, row["VISIT"], row["UNI"]))
                self.assertEqual(root.tag, "RECEIPT")


if __name__ == "__main__":
    unittest.main()
