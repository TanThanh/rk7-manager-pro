import unittest
from pathlib import Path

from rk7_pro.core.udb_checkview_service import UdbCheckViewService
from web_bridge import WebBridgeAPI


ROOT = Path(__file__).resolve().parents[2]


class ShiftHandoverReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = UdbCheckViewService()
        cls.sh01372 = cls.service.parse_udb_database(ROOT / "sh01372.udb")
        cls.shift64 = cls.service.parse_udb_database(ROOT / "shift.64.udb")

    def test_sh01372_default_shift_report_balances(self):
        rep = self.service.get_shift_handover_report(self.sh01372)
        self.assertTrue(rep["success"])
        self.assertEqual(rep["selected_shift"], "418")
        self.assertEqual(rep["header"]["form_code"], "FO.201")
        self.assertEqual(rep["header"]["shift_date"], "20.07.2026")

        rev = rep["revenue"]
        self.assertEqual(rev["gross_revenue"], 22496784.0)
        self.assertEqual(rev["total_discount"], -205800.0)
        self.assertEqual(rev["vat"], 1681984.0)
        self.assertEqual(rev["pre_tax"], 20814800.0)
        self.assertEqual(rev["pre_tax"] + rev["vat"], rev["gross_revenue"])

        stats = rep["stats"]
        self.assertEqual(stats["paid_total"], rev["gross_revenue"])
        self.assertEqual(stats["paid_checks_count"], 15)
        self.assertEqual(stats["paid_guests"], 48)
        self.assertEqual(stats["unpaid_total"], 2210680.0)
        self.assertEqual(stats["unpaid_checks_count"], 1)
        self.assertEqual(stats["unpaid_guests"], 4)
        self.assertEqual(stats["discount_total"], -205800.0)
        self.assertEqual(stats["begin_bill"], 1)
        self.assertEqual(stats["end_bill"], 15)

        curr_total = sum(g["total"] for g in rep["currency_groups"])
        self.assertEqual(curr_total, rev["gross_revenue"])
        self.assertIn("BÁO CÁO GIAO CA THU NGÂN", rep["k80_text"])
        self.assertIn("22,496,784", rep["k80_text"])

    def test_shift64_splits_shifts_9_and_10_and_all(self):
        rep9 = self.service.get_shift_handover_report(self.shift64, shift_num="9")
        self.assertEqual(rep9["selected_shift"], "9")
        self.assertEqual(rep9["revenue"]["gross_revenue"], 139303570.0)
        self.assertEqual(rep9["revenue"]["total_discount"], -222250.0)
        self.assertEqual(rep9["stats"]["discount_total"], -222250.0)
        self.assertEqual(rep9["stats"]["paid_checks_count"], 45)
        self.assertEqual(rep9["stats"]["begin_bill"], 1)
        self.assertEqual(rep9["stats"]["end_bill"], 43)

        rep10 = self.service.get_shift_handover_report(self.shift64, shift_num="10")
        self.assertEqual(rep10["selected_shift"], "10")
        self.assertEqual(rep10["revenue"]["gross_revenue"], 482764120.0)
        self.assertEqual(rep10["revenue"]["total_discount"], -7507000.0)
        self.assertEqual(rep10["stats"]["discount_total"], -7507000.0)
        self.assertEqual(rep10["stats"]["paid_checks_count"], 153)
        self.assertEqual(rep10["stats"]["begin_bill"], 44)
        self.assertEqual(rep10["stats"]["end_bill"], 194)

        rep_all = self.service.get_shift_handover_report(self.shift64, shift_num="ALL")
        self.assertEqual(rep_all["selected_shift"], "ALL")
        self.assertEqual(
            rep_all["revenue"]["gross_revenue"],
            rep9["revenue"]["gross_revenue"] + rep10["revenue"]["gross_revenue"],
        )
        self.assertEqual(rep_all["header"]["employee_name"], "Tất cả ca")

    def test_web_bridge_shift_report_method(self):
        api = WebBridgeAPI(data_dir=ROOT)
        empty_res = api.checkview_get_shift_report()
        self.assertFalse(empty_res["success"])

        loaded = api.checkview_load_file(str(ROOT / "sh01372.udb"))
        self.assertTrue(loaded["success"])
        rep = api.checkview_get_shift_report()
        self.assertTrue(rep["success"])
        self.assertEqual(rep["revenue"]["gross_revenue"], 22496784.0)

    def test_fallback_when_paybindings_empty(self):
        synthetic = {
            "filename": "synthetic.udb",
            "header": {"shift_num": "1", "shift_date": "11.11.2026", "restaurant": "9999999"},
            "_raw_tables": {
                "PRINTCHECKS": [
                    {"VISIT": "1", "UNI": "10", "STATE": "6", "ISHIFT": "1", "PRINTNUMBER": "5", "GUESTCNT": "2", "BASICSUM": "10800000", "TAXSUMADDED": "800000", "DISCOUNTSUM": "0"},
                ],
                "PAYMENTS": [
                    {"VISIT": "1", "STATE": "6", "ISHIFT": "1", "SIFR": "1", "IHIGHLEVELTYPE": "103", "PAYLINETYPE": "0", "BASICSUM": "10800000", "ORIGINALSUM": "10800000"},
                ],
                "SHIFTS": [{"SHIFTNUM": "1", "ICOMMONSHIFT": "1", "CLOSED": "1"}],
                "GLOBALSHIFTS": [{"SHIFTNUM": "1", "SHIFTDATE": "11.11.2026"}],
            },
        }
        rep = self.service.get_shift_handover_report(synthetic)
        self.assertEqual(rep["data_source"], "PRINTCHECKS")
        self.assertEqual(rep["revenue"]["gross_revenue"], 108000.0)
        self.assertEqual(rep["revenue"]["vat"], 8000.0)
        self.assertEqual(rep["revenue"]["pre_tax"], 100000.0)
        self.assertEqual(rep["stats"]["begin_bill"], 5)
        self.assertEqual(rep["stats"]["end_bill"], 5)

    def test_booking_id_extracted_for_cvl_checks_and_detail(self):
        check_115378 = next(c for c in self.shift64["checks"] if c["check_num"] == "115378")
        self.assertEqual(check_115378["booking_id"], "CVL-MRN-271026-WXF")

        detail = self.service.get_check_view_detail(self.shift64, check_115378["visit_id"], check_115378["check_uni"])
        self.assertEqual(detail["booking_id"], "CVL-MRN-271026-WXF")
        self.assertEqual(detail["booking"]["deposit"], 500000.0)
        self.assertEqual(detail["booking"]["note"], "16 C THẢO")
        self.assertEqual(detail["booking"]["phone"], "0975112784")

        # Non-booking UDB leaves booking_id empty
        sh_check = self.sh01372["checks"][0]
        self.assertEqual(sh_check["booking_id"], "")
        sh_detail = self.service.get_check_view_detail(self.sh01372, sh_check["visit_id"], sh_check["check_uni"])
        self.assertEqual(sh_detail["booking_id"], "")


if __name__ == "__main__":
    unittest.main()
