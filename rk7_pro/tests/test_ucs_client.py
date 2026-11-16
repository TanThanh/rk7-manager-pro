import tempfile
import unittest
from pathlib import Path

from rk7_pro.ucs_client import (
    UCS_TOOLS_URL, UcsClient, UcsUploadError, discover_action_form,
    discover_upload_form, parse_ucs_result,
    parse_ucs_table,
)


UPLOAD_HTML = """
<html><form method="post" action="/udbtools/" enctype="multipart/form-data">
<input type="hidden" name="_csrf" value="csrf-value">
<input type="file" name="dbfile"><button type="submit">Upload</button>
</form></html>
"""

RESULT_HTML = """
<html><body><h1>Midserver (UDB)</h1>
<p>Uploaded DB type: UDB</p>
<a href="/uploaded/example/work.udb">work.udb</a>
<p>Version DB structure: 76400023</p>
<p>This is work DB, not shift!</p>
<div>Tables (3):</div><ul>
<li><a href="./?linkfile=/uploaded/work.abs&amp;action=showdbtable&amp;table=ACTIVITYLIST">ACTIVITYLIST</a> (8)</li>
<li><a href="./?linkfile=/uploaded/work.abs&amp;action=showdbtable&amp;table=CASHINOUT">CASHINOUT</a> (0)</li>
<li><a href="./?linkfile=/uploaded/work.abs&amp;action=showdbtable&amp;table=VISITS">VISITS</a> (76)</li>
</ul></body></html>
"""

TABLE_HTML = """<html><h3>ACTIVITYLIST (2)</h3><table><tr><th>ID</th><th>NAME</th></tr>
<tr><td>1</td><td>Sample</td></tr><tr><td>2</td><td>Second</td></tr></table></html>"""

UDB_PAGE = """<p>Uploaded DB type: UDB</p><form method="post">
<input type="hidden" name="_csrf" value="csrf1">
<input type="hidden" name="linkfile" value="/uploaded/work.udb">
<input type="hidden" name="action" value="udb2abs"></form>"""
ABS_PAGE = """<p>Uploaded DB type: ABS</p><form method="post" action="index.php">
<input type="hidden" name="_csrf" value="csrf2">
<input type="hidden" name="linkfile" value="/uploaded/work.abs">
<input type="radio" name="action" value="showdbinfo"></form>"""


class FakeResponse:
    def __init__(self, text, status_code=200, headers=None):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError("Unexpected status")


class FakeSession:
    def __init__(self):
        self.auth = None
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if 'table=ACTIVITYLIST' in url:
            return FakeResponse(TABLE_HTML)
        if 'table=CASHINOUT' in url:
            return FakeResponse('<h3>CASHINOUT (0)</h3><table><thead><tr><td>ID</td></tr></thead></table>')
        if method == "GET":
            return FakeResponse(UPLOAD_HTML)
        fields = dict(kwargs.get("data", []))
        if "files" in kwargs:
            return FakeResponse(UDB_PAGE)
        if fields.get("action") == "udb2abs":
            return FakeResponse(ABS_PAGE)
        if fields.get("action") == "showdbinfo":
            return FakeResponse(RESULT_HTML.replace("Uploaded DB type: UDB", "Uploaded DB type: ABS"))
        raise AssertionError("Unexpected UCS action")

    def close(self):
        pass


class UcsClientTests(unittest.TestCase):
    def test_form_discovers_file_and_csrf(self):
        target, file_field, fields = discover_upload_form(UPLOAD_HTML, UCS_TOOLS_URL)
        self.assertEqual(target, UCS_TOOLS_URL)
        self.assertEqual(file_field, "dbfile")
        self.assertEqual(fields, [("_csrf", "csrf-value")])

    def test_form_rejects_external_action(self):
        html = UPLOAD_HTML.replace('/udbtools/', 'https://other.example/upload')
        with self.assertRaises(UcsUploadError):
            discover_upload_form(html, UCS_TOOLS_URL)

    def test_result_reads_actual_table_counts(self):
        result = parse_ucs_result(RESULT_HTML)
        self.assertEqual(result["db_type"], "UDB")
        self.assertEqual(result["declared_table_count"], 3)
        self.assertEqual(result["empty_table_count"], 1)
        self.assertEqual(result["largest_tables"][0], {"name": "VISITS", "rows": 76})

    def test_result_keeps_extra_rendered_table_when_declared_count_differs(self):
        html = RESULT_HTML.replace("Tables (3)", "Tables (2)")
        result = parse_ucs_result(html)
        self.assertEqual(result["declared_table_count"], 2)
        self.assertEqual(len(result["tables"]), 3)

    def test_conversion_and_db_info_forms(self):
        target, fields = discover_action_form(UDB_PAGE, UCS_TOOLS_URL, "udb2abs")
        self.assertEqual(target, UCS_TOOLS_URL)
        self.assertEqual(dict(fields)["action"], "udb2abs")
        target, fields = discover_action_form(ABS_PAGE, UCS_TOOLS_URL, "showdbinfo")
        self.assertEqual(target, UCS_TOOLS_URL + "index.php")
        self.assertEqual(dict(fields)["linkfile"], "/uploaded/work.abs")
        with self.assertRaises(UcsUploadError):
            discover_action_form(ABS_PAGE, UCS_TOOLS_URL, "cleardup")

    def test_ucs_td_header_and_missing_trailing_cell(self):
        html = ("<h3>PRINTCHECKS (1)</h3><table><tr><td>Select</td><td>VISIT</td><td>MIDSERVER</td>"
                "<td>GLOBALFISCALID</td></tr><tr><td><input type='checkbox'></td>"
                "<td>123</td><td>server</td></tr></table>")
        table = parse_ucs_table(html, "PRINTCHECKS")
        self.assertEqual(table["columns"],
                         ["Select", "VISIT", "MIDSERVER", "GLOBALFISCALID"])
        self.assertEqual(table["rows"], [["", "123", "server", ""]])

    def test_thead_marks_mixed_case_labels_as_header(self):
        html = "<h3>VISITS (1)</h3><table><thead><tr><td>Visit ID</td><td>State</td></tr></thead><tbody><tr><td>1</td><td>OK</td></tr></tbody></table>"
        table = parse_ucs_table(html, "VISITS")
        self.assertEqual(table["columns"], ["Visit ID", "State"])
        self.assertEqual(table["rows"], [["1", "OK"]])

    def test_upload_uses_discovered_form_and_returns_analysis(self):
        session = FakeSession()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "work.udb"
            path.write_bytes(b"sample")
            result = UcsClient(session=session).upload_and_analyze(path, "dealer", "secret")
        self.assertEqual(result["file"], "work.udb")
        self.assertEqual([call[0] for call in session.calls[:4]], ["GET", "POST", "POST", "POST"])
        post = session.calls[1]
        self.assertEqual(post[1], UCS_TOOLS_URL)
        self.assertEqual(post[2]["data"], [("_csrf", "csrf-value")])
        self.assertIn("dbfile", post[2]["files"])
        self.assertIsNotNone(session.auth)
        self.assertEqual(result["db_type"], "ABS")
        self.assertGreaterEqual(result["timings_seconds"]["upload"], 0)
        self.assertEqual([dict(call[2]["data"])["action"] for call in session.calls[2:4]],
                         ["udb2abs", "showdbinfo"])
        self.assertEqual(result["loaded_table_count"], 2)
        self.assertEqual(result["complete_table_count"], 1)
        self.assertEqual(result["readable_tables"], ["ACTIVITYLIST", "CASHINOUT", "VISITS"])
        self.assertEqual(result["table_data"]["CASHINOUT"]["columns"], ["ID"])
        self.assertEqual(result["table_data"]["CASHINOUT"]["rows"], [])

    def test_selected_table_reads_rows_from_returned_link(self):
        session = FakeSession()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "work.udb"
            path.write_bytes(b"sample")
            client = UcsClient(session=session)
            client.upload_and_analyze(path, "dealer", "secret")
            table = client.fetch_table("ACTIVITYLIST")
            self.assertEqual(table["columns"], ["ID", "NAME"])
            self.assertEqual(table["rows"], [["1", "Sample"], ["2", "Second"]])
            with self.assertRaises(UcsUploadError):
                client.fetch_table("UNKNOWN")
            client.close()
        self.assertIsNone(session.auth)

    def test_upload_can_return_db_info_before_table_downloads(self):
        session = FakeSession()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "work.udb"
            path.write_bytes(b"sample")
            client = UcsClient(session=session)
            result = client.upload_and_analyze(path, "dealer", "secret", fetch_tables=False)
            self.assertEqual(result["table_data"], {})
            self.assertEqual(result["loaded_table_count"], 0)
            self.assertEqual(len(session.calls), 4)

    def test_external_redirect_is_blocked(self):
        session = FakeSession()
        session.request = lambda *_args, **_kwargs: FakeResponse('', 302, {'Location': 'https://other.example/upload'})
        with self.assertRaises(UcsUploadError):
            UcsClient(session=session)._request('GET', UCS_TOOLS_URL)

    def test_repair_receipttaxtype_and_enums(self):
        from rk7_pro.ucs_client import repair_rk7_vietnamese
        self.assertEqual(repair_rk7_vietnamese("0 general îáùåå"), "0 general (Thuế phổ thông / OSN)")
        self.assertEqual(repair_rk7_vietnamese("0 general общее"), "0 general (Thuế phổ thông / OSN)")
        self.assertEqual(repair_rk7_vietnamese("1 simplified"), "1 simplified (Thuế đơn giản DT / USN)")



if __name__ == "__main__":
    unittest.main()
