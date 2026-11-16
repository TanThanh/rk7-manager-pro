import unittest
from pathlib import Path

from rk7_pro.core.udb_checkview_service import UdbCheckViewService


ROOT = Path(__file__).resolve().parents[2]


class UdbXmlRepairTest(unittest.TestCase):
    def test_invalid_numeric_references_do_not_block_work_udb(self):
        service = UdbCheckViewService()
        result = service.parse_udb_database(ROOT / "work47712.udb")
        self.assertEqual(result["header"]["invalid_xml_refs_removed"], 3)
        self.assertEqual(len(result["checks"]), 63)

    def test_valid_udb_is_unchanged(self):
        service = UdbCheckViewService()
        result = service.parse_udb_database(ROOT / "sh00288.udb")
        self.assertEqual(result["header"]["invalid_xml_refs_removed"], 0)
        self.assertEqual(len(result["checks"]), 81)


if __name__ == "__main__":
    unittest.main()
