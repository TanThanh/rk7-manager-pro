import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from web_bridge import WebBridgeAPI


class UcsBridgeTests(unittest.TestCase):
    def test_file_selection_and_direct_upload_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.udb'
            path.write_bytes(b'sample')
            api = WebBridgeAPI.__new__(WebBridgeAPI)
            api._window = MagicMock()
            api._window.create_file_dialog.return_value = [str(path)]
            api._ucs_selected_file = None
            api._ucs_client = None
            api._ucs_analysis = None
            selected = api.ucs_select_file()
            self.assertTrue(selected['success'])
            self.assertEqual(selected['filename'], 'sample.udb')
            with patch('web_bridge.UcsClient') as client_type:
                client_type.return_value.upload_and_analyze.return_value = {'tables': [{'name': 'PRINTCHECKS', 'rows': 2}]}
                result = api.ucs_upload_and_analyze('dealer', 'secret')
                self.assertTrue(result['success'])
                client_type.return_value.upload_and_analyze.assert_called_once_with(path, 'dealer', 'secret', fetch_tables=False)
                client_type.return_value.fork_for_table_reads.return_value.fetch_table_summary.return_value = {'rows': []}
                table = api.ucs_read_table('PRINTCHECKS')
                self.assertTrue(table['success'])
                client_type.return_value.fork_for_table_reads.return_value.fetch_table_summary.assert_called_once_with('PRINTCHECKS', 2)


if __name__ == '__main__':
    unittest.main()
