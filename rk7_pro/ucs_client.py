"""Direct, read-only UDB analysis through the authenticated UCS upload form."""

import re
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from requests.auth import HTTPBasicAuth

UCS_ORIGIN = "https://utils.ucs.ru"
UCS_TOOLS_URL = UCS_ORIGIN + "/udbtools/"
MAX_RESULT_BYTES = 12 * 1024 * 1024
MAX_TABLE_ROWS = 50_000

# Mapping table to restore Vietnamese CP1258/CP1252 text misinterpreted by UCS tools as CP1251 Cyrillic
_CP1251_TO_CP1258 = {}
for _b in range(128, 256):
    _byte = bytes([_b])
    try:
        _c1251 = _byte.decode("cp1251")
        _c1258 = _byte.decode("cp1258")
        _CP1251_TO_CP1258[_c1251] = _c1258
    except Exception:
        pass


# Known UCS status & enum descriptions in Russian translated to clean English/Vietnamese
_UCS_ENUM_TRANSLATIONS = [
    # TDrawItemState
    (re.compile(r'\b6\s+disClosed\s+закрыто/оплачено\b', re.I), '6 disClosed (Đã đóng / thanh toán)'),
    (re.compile(r'\b0\s+disNone\s+не определено\b', re.I), '0 disNone (Chưa xác định)'),
    (re.compile(r'\b1\s+disOpened\s+открыто\b', re.I), '1 disOpened (Đang mở)'),
    (re.compile(r'\b2\s+disLocked\s+заблокировано\b', re.I), '2 disLocked (Đã khóa)'),
    (re.compile(r'\b3\s+disFixed\s+зафиксировано\b', re.I), '3 disFixed (Đã chốt)'),
    (re.compile(r'\b4\s+disPrinted\s+напечатано\b', re.I), '4 disPrinted (Đã in)'),
    (re.compile(r'\b5\s+disPartClosed\s+закрыто частично\b', re.I), '5 disPartClosed (Đóng một phần)'),
    (re.compile(r'\b7\s+disDeleted\s+удалено\b', re.I), '7 disDeleted (Đã xóa)'),
    # TPayLineType
    (re.compile(r'\b0\s+pltCash\s+наличные\b', re.I), '0 pltCash (Tiền mặt)'),
    (re.compile(r'\b1\s+pltCrCard\s+банковская карта\b', re.I), '1 pltCrCard (Thẻ ngân hàng)'),
    (re.compile(r'\b2\s+pltHotel\s+на номер в отеле\b', re.I), '2 pltHotel (Phòng khách sạn)'),
    (re.compile(r'\b3\s+pltPayCard\s+плат[её]жная карта\b', re.I), '3 pltPayCard (Thẻ thanh toán/PDS)'),
    (re.compile(r'\b4\s+pltCashExclude\s+фиктивная сдача\b', re.I), '4 pltCashExclude (Tiền thừa ảo)'),
    (re.compile(r'\b5\s+pltOtherNonCash\s+прочий безналичный\b', re.I), '5 pltOtherNonCash (Không tiền mặt khác)'),
    # TSessionType (ORDERSESSIONS.ISESSIONTYPE)
    (re.compile(r'\b0\s+stAuto(?:\s+пакет\s+создан\s+автоматически)?\b', re.I), '0 stAuto (Tự động tạo)'),
    (re.compile(r'\b1\s+stManual(?:\s+пакет\s+создан\s+вручную)?\b', re.I), '1 stManual (Thủ công)'),
    (re.compile(r'\b2\s+stTransferIn(?:\s*\([^)]*\))?(?:\s+перенесен[^<>\n\r]*)?\b', re.I), '2 stTransferIn (Chuyển vào từ order khác)'),
    (re.compile(r'\b3\s+stTransferShift(?:\s+пакет\s+перенесен\s+из\s+другой\s+смены[^<>\n\r]*)?\b', re.I), '3 stTransferShift (Chuyển từ ca trước sang)'),
    (re.compile(r'\b4\s+stTransferUnion(?:\s+перенесен\s+при\s+объединении[^<>\n\r]*)?\b', re.I), '4 stTransferUnion (Chuyển khi gộp order)'),
    (re.compile(r'\b5\s+stXML(?:\s+пакет\s+создан\s+по\s+XML[^<>\n\r]*)?\b', re.I), '5 stXML (Tạo qua lệnh XML)'),
    (re.compile(r'\b6\s+stTransferReturn(?:\s+возврат[^<>\n\r]*)?\b', re.I), '6 stTransferReturn (Chuyển trả món/hoàn tiền)'),
    # Fiscal PAYMENTMETHOD (PAYBINDINGS.PAYMENTMETHOD)
    (re.compile(r'\b4\s+Full\s+calculation(?:\s+полный\s+расчет)?\b', re.I), '4 Full calculation (Thanh toán toàn bộ)'),
    (re.compile(r'\b1\s+Full\s+prepayment(?:\s+полная\s+предоплата)?\b', re.I), '1 Full prepayment (Trả trước 100%)'),
    (re.compile(r'\b2\s+Prepayment(?:\s+частичная\s+предоплата)?\b', re.I), '2 Prepayment (Trả trước một phần)'),
    (re.compile(r'\b3\s+Advance(?:\s+аванс)?\b', re.I), '3 Advance (Tạm ứng / Đặt cọc)'),
    (re.compile(r'\b5\s+Partial\s+payment\s+and\s+credit(?:\s+частичный\s+расчет\s+и\s+кредит)?\b', re.I), '5 Partial payment & credit (Thanh toán 1 phần & nợ)'),
    (re.compile(r'\b6\s+Credit\s+transfer(?:\s+передача\s+в\s+кредит)?\b', re.I), '6 Credit transfer (Ghi nợ)'),
    (re.compile(r'\b7\s+Credit\s+payment(?:\s+оплата\s+кредита)?\b', re.I), '7 Credit payment (Thanh toán khoản nợ)'),
    # RECEIPTTAXTYPE (PRINTCHECKS.RECEIPTTAXTYPE - Hệ thống thuế / Loại thuế bill)
    (re.compile(r'\b0\s+general(?:\s+(?:общее|îáùåå))?\b', re.I), '0 general (Thuế phổ thông / OSN)'),
    (re.compile(r'\b1\s+simplified(?:\s+(?:упрощенная(?:\s+доход)?|упрощ[её]нная))?\b', re.I), '1 simplified (Thuế đơn giản DT / USN)'),
    (re.compile(r'\b2\s+simplified[_\s]expense(?:\s+(?:упрощенная(?:\s+доход-расход)?|упрощ[её]нная))?\b', re.I), '2 simplified_expense (Thuế đơn giản DT-CP / USN)'),
    (re.compile(r'\b3\s+single[_\s]imputed(?:\s+(?:ЕНВД|вмененный))?\b', re.I), '3 single_imputed (Thuế ấn định / ENVD)'),
    (re.compile(r'\b4\s+agriculture(?:\s+(?:ЕСХН|сельхоз))?\b', re.I), '4 agriculture (Thuế nông nghiệp / ESHN)'),
    (re.compile(r'\b5\s+patent(?:\s+(?:патент|патентная))?\b', re.I), '5 patent (Thuế khoán / Patent)'),
    (re.compile(r'\bgeneral\s+(?:общее|îáùåå)\b', re.I), 'general (Thuế phổ thông / OSN)'),
    # Common UI enums
    (re.compile(r'\bitManual\s+вручную\b', re.I), 'itManual (Thủ công)'),
    (re.compile(r'\bstAuto\s+пакет создан автоматически\b', re.I), 'stAuto (Tự động tạo)'),
    (re.compile(r'\bpfNow\s+печать при первой возможности\b', re.I), 'pfNow (In ngay khi có thể)'),
    (re.compile(r'\bpfPrinted\s+уже отправлено на печать\b', re.I), 'pfPrinted (Đã gửi in)'),
    (re.compile(r'\bRegular\s+order\s+обычный заказ\b', re.I), 'Regular order (Order thường)'),
    (re.compile(r'\bkdsNone\s+нет статуса\b', re.I), 'kdsNone (Chưa có trạng thái)'),
    (re.compile(r'\bkdsSent\s+отправлено\b', re.I), 'kdsSent (Đã gửi bếp)'),
]


def repair_rk7_vietnamese(text):
    """Repair Vietnamese text and translate native UCS Cyrillic enum strings."""
    if not text or not isinstance(text, str):
        return text
    # 1. Translate known UCS Russian enum strings to clean bilingual labels first
    for pattern, repl in _UCS_ENUM_TRANSLATIONS:
        text = pattern.sub(repl, text)
    # Fast check: does text contain any remaining Cyrillic characters?
    if not any("\u0400" <= ch <= "\u04ff" for ch in text):
        return text
    converted = [_CP1251_TO_CP1258.get(ch, ch) for ch in text]
    return unicodedata.normalize("NFC", "".join(converted))


class UcsUploadError(Exception):
    """A user-facing UCS connection, authentication, or form error."""


def _ucs_url(url):
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname == "utils.ucs.ru"
                and parts.port in (None, 443) and not parts.username and not parts.password)
    except (ValueError, AttributeError):
        return False


def _safe_control(value):
    """Keep control syntax for diagnostics without exporting long token values."""
    value = re.sub(r"[A-Za-z0-9_-]{24,}", "[redacted]", str(value or ""))
    return value[:240]


class _FormReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {"action": attrs.get("action", ""),
                            "method": attrs.get("method", "GET").upper(),
                            "enctype": attrs.get("enctype", "").lower(),
                            "fields": [], "file_fields": [], "submit_fields": [],
                            "actions": []}
        elif self.current is not None and tag == "input":
            name = attrs.get("name", "")
            kind = attrs.get("type", "text").lower()
            if kind == "file" and name:
                self.current["file_fields"].append(name)
            elif kind == "hidden" and name:
                self.current["fields"].append((name, attrs.get("value", "")))
            elif kind == "submit" and name:
                self.current["submit_fields"].append((name, attrs.get("value", "")))
            elif kind == "radio" and name == "action":
                self.current["actions"].append(attrs.get("value", ""))
        elif self.current is not None and tag == "button" and attrs.get("name"):
            self.current["submit_fields"].append((attrs["name"], attrs.get("value", "")))

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None


class _ResultReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.files = []
        self.links = []
        self._href = None
        self._onclick = None
        self._attributes = {}
        self._link_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attributes = dict(attrs)
            self._href = attributes.get("href") or ""
            self._onclick = attributes.get("onclick") or ""
            self._attributes = {key: _safe_control(value) for key, value in attributes.items()
                                if key in ("id", "class", "role", "data-action", "data-table")}
            self._link_parts = []
        if tag in ("br", "p", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)
        if self._href is not None:
            self._link_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            name = "".join(self._link_parts).strip()
            self.links.append((name, self._href, self._onclick, self._attributes))
            if re.search(r"\.(?:udb|abs)$", name, re.I):
                self.files.append(name)
            self._href = None
        if tag in ("p", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")


def discover_upload_form(html, page_url):
    reader = _FormReader()
    reader.feed(html)
    candidates = [form for form in reader.forms
                  if form["method"] == "POST" and form["file_fields"]
                  and "multipart/form-data" in form["enctype"]]
    if len(candidates) != 1 or len(candidates[0]["file_fields"]) != 1:
        raise UcsUploadError("Could not identify one safe UDB upload form on UCS.")
    form = candidates[0]
    if len(form["submit_fields"]) > 1:
        raise UcsUploadError("UCS upload form has multiple actions; the tool stopped to avoid choosing one incorrectly.")
    target = urljoin(page_url, form["action"] or page_url)
    if not _ucs_url(target):
        raise UcsUploadError("UCS upload form points outside the approved HTTPS site.")
    return target, form["file_fields"][0], form["fields"] + form["submit_fields"]


def discover_action_form(html, page_url, action):
    """Find one UCS POST form advertising a specific conversion/read action."""
    reader = _FormReader()
    reader.feed(html)
    matches = []
    for form in reader.forms:
        if form["method"] != "POST" or form["file_fields"]:
            continue
        fields = dict(form["fields"])
        if fields.get("action") != action and action not in form["actions"]:
            continue
        if not fields.get("_csrf") or not fields.get("linkfile"):
            continue
        target = urljoin(page_url, form["action"] or page_url)
        if not _ucs_url(target):
            continue
        matches.append((target, [(key, value) for key, value in form["fields"]
                                 if key in ("_csrf", "linkfile")]
                        + [("action", action)]))
    if len(matches) != 1:
        raise UcsUploadError(f"UCS did not provide one safe {action} action form.")
    return matches[0]


def parse_ucs_result(html):
    reader = _ResultReader()
    reader.feed(html)
    text = "".join(reader.parts)
    compact = re.sub(r"[ \t]+", " ", text)

    def field(pattern):
        match = re.search(pattern, compact, re.I)
        return match.group(1).strip() if match else ""

    db_type = field(r"Uploaded\s+DB\s+type\s*:\s*([^\r\n]+)")
    structure = field(r"Version\s+DB\s+structure\s*:\s*([^\r\n]+)")
    program = field(r"Version\s+RK7\s+program\s*:\s*([^\r\n]+)")
    tables_heading = re.search(r"Tables\s*\(\s*(\d+)\s*\)", compact, re.I)
    declared = tables_heading.group(1) if tables_heading else ""
    # The declared count can differ from the actual <li> count. UCS has been
    # observed to declare 51 while rendering 52 table links.
    table_list = re.search(r"Tables\s*\(\s*\d+\s*\)\s*:(.*?)</ul>", html, re.I | re.S)
    table_text = ""
    if table_list:
        items = re.findall(r"<li\b[^>]*>(.*?)</li>", table_list.group(1), re.I | re.S)
        table_text = "\n".join(re.sub(r"<[^>]*>", " ", item) for item in items)
    elif tables_heading:
        table_text = compact[tables_heading.end():]
    tables = []
    seen = set()
    for name, rows in re.findall(r"\b([A-Z][A-Z0-9_]{1,80})\s*\(\s*(\d+)\s*\)", table_text):
        if name not in seen and len(tables) < 1000:
            seen.add(name)
            tables.append({"name": name, "rows": int(rows)})
    if not db_type or not declared or not tables:
        raise UcsUploadError("UCS returned a page, but no database analysis was found. Check the file and account access.")
    return {
        "file": reader.files[0] if reader.files else "",
        "db_type": db_type,
        "structure_version": structure,
        "program_version": program,
        "is_work_db": bool(re.search(r"This\s+is\s+work\s+DB", compact, re.I)),
        "declared_table_count": int(declared),
        "tables": tables,
        "empty_table_count": sum(table["rows"] == 0 for table in tables),
        "largest_tables": sorted(tables, key=lambda table: table["rows"], reverse=True)[:10],
    }


class _TableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.current = None
        self.row = None
        self.cell = None
        self.cell_kind = None
        self.truncated = False
        self.in_thead = False
        self.header_rows = set()
        self.heading = None
        self.heading_parts = None
        self.table_headings = []

    def handle_starttag(self, tag, _attrs):
        if tag == "h3":
            self.heading_parts = []
        elif tag == "thead" and self.current is not None:
            self.in_thead = True
        elif tag == "table" and self.current is None:
            self.current = []
        elif tag == "tr" and self.current is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.cell_kind = tag
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_data(self, data):
        if self.heading_parts is not None:
            self.heading_parts.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append({"kind": self.cell_kind, "value": " ".join("".join(self.cell).split())[:2000]})
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.current) < MAX_TABLE_ROWS + 1:
                if self.in_thead:
                    self.header_rows.add((len(self.tables), len(self.current)))
                self.current.append(self.row)
            else:
                self.truncated = True
            self.row = None
        elif tag == "table" and self.current is not None:
            self.tables.append(self.current)
            self.table_headings.append(self.heading)
            self.current = None
        elif tag == "thead":
            self.in_thead = False
        elif tag == "h3" and self.heading_parts is not None:
            self.heading = " ".join("".join(self.heading_parts).split())
            self.heading_parts = None


def parse_ucs_table(html, name):
    reader = _TableReader()
    reader.feed(html)
    if not reader.tables:
        raise UcsUploadError("UCS did not return a readable HTML table for this selection.")
    matching = [(index, table) for index, table in enumerate(reader.tables)
                if re.match(rf"^{re.escape(name)}\s*\(\s*\d+\s*\)",
                            reader.table_headings[index] or "", re.I)]
    if not matching:
        raise UcsUploadError(f"UCS did not return the {name} table content.")
    table_index, rows = max(matching, key=lambda item: len(item[1]))
    if not rows:
        return {"name": name, "columns": [], "rows": [], "truncated": False}
    first = rows[0]
    labels = [cell["value"] for cell in first]
    # UCS uses <td> for schema headers (including PRINTCHECKS). The first
    # data row contains a selection checkbox; its header is the word Select.
    schema_labels = [label for label in labels if label and label != "Select"]
    first_is_header = (table_index, 0) in reader.header_rows or all(cell["kind"] == "th" for cell in first) or (
        len(rows) > 1 and len(schema_labels) >= 2
        and len(schema_labels) >= len(labels) - 1
        and all(re.fullmatch(r"[A-Z][A-Z0-9_]*", label) for label in schema_labels)
    )
    columns = labels if first_is_header else [f"Column {i + 1}" for i in range(len(first))]
    data_rows = rows[1:] if first_is_header else rows
    values = [[repair_rk7_vietnamese(cell["value"]) for cell in row] for row in data_rows[:MAX_TABLE_ROWS]]
    # Preserve column positions even when UCS omits trailing empty <td> cells.
    if first_is_header:
        values = [row + [""] * max(0, len(columns) - len(row)) for row in values]
    return {"name": name, "columns": columns,
            "rows": values,
            "truncated": reader.truncated or len(data_rows) > MAX_TABLE_ROWS}


class UcsClient:
    def __init__(self, session=None, base_url=UCS_TOOLS_URL):
        self.session = session or requests.Session()
        self.base_url = base_url
        self._table_urls = {}
        if not _ucs_url(base_url):
            raise UcsUploadError("Invalid UCS HTTPS address.")

    def _request(self, method, url, timeout=(15, 180), **kwargs):
        if not _ucs_url(url):
            raise UcsUploadError("Blocked a request outside the UCS HTTPS site.")
        for _ in range(5):
            response = self.session.request(method, url, allow_redirects=False,
                                            timeout=timeout, **kwargs)
            if response.status_code in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers.get("Location", ""))
                if not _ucs_url(target):
                    raise UcsUploadError("UCS redirected outside the approved HTTPS site.")
                if method == "POST" and response.status_code in (307, 308):
                    raise UcsUploadError("UCS requested a repeated upload; the tool stopped to avoid sending the file twice.")
                method, url = "GET", target
                kwargs = {}
                continue
            return response, url
        raise UcsUploadError("UCS redirected too many times.")

    def verify_credentials(self, username, password):
        if not username or not password:
            raise UcsUploadError("Enter your UCS username and password.")
        self.session.auth = HTTPBasicAuth(username, password)
        page, _ = self._request("GET", self.base_url)
        if page.status_code in (401, 403):
            raise UcsUploadError("UCS rejected the username or password.")
        page.raise_for_status()
        return True

    def upload_and_analyze(self, path, username, password, fetch_tables=True):
        started_at = time.perf_counter()
        file_path = Path(path)
        if not file_path.is_file() or file_path.suffix.lower() != ".udb":
            raise UcsUploadError("Choose an existing .udb file.")
        if not username or not password:
            raise UcsUploadError("Enter your UCS username and password.")
        self.session.auth = HTTPBasicAuth(username, password)
        try:
            page, page_url = self._request("GET", self.base_url)
            if page.status_code in (401, 403):
                raise UcsUploadError("UCS rejected the username or password.")
            page.raise_for_status()
            form_page_url = page_url
            try:
                target, file_field, hidden_fields = discover_upload_form(page.text, page_url)
            except UcsUploadError:
                home, home_url = self._request("GET", UCS_ORIGIN + "/")
                if home.status_code in (401, 403):
                    raise UcsUploadError("UCS rejected the username or password.")
                home.raise_for_status()
                target, file_field, hidden_fields = discover_upload_form(home.text, home_url)
                form_page_url = home_url
            with file_path.open("rb") as stream:
                result, result_url = self._request("POST", target, data=hidden_fields,
                    files={file_field: (file_path.name, stream, "application/octet-stream")},
                    headers={"Origin": UCS_ORIGIN, "Referer": form_page_url, "Accept": "text/html"})
            if result.status_code in (401, 403):
                raise UcsUploadError("UCS authentication expired during upload.")
            result.raise_for_status()
            if len(result.content) > MAX_RESULT_BYTES:
                raise UcsUploadError("UCS result page is too large to analyze safely.")
            upload_seconds = time.perf_counter() - started_at
            db_type_match = re.search(r"Uploaded\s+DB\s+type\s*:\s*(UDB|ABS)\b",
                                      result.text, re.I)
            if not db_type_match:
                raise UcsUploadError("UCS did not confirm the uploaded database type.")
            if db_type_match.group(1).upper() == "UDB":
                convert_url, convert_fields = discover_action_form(result.text, result_url, "udb2abs")
                result, result_url = self._request("POST", convert_url, data=convert_fields,
                    headers={"Origin": UCS_ORIGIN, "Referer": result_url, "Accept": "text/html"})
                if result.status_code in (401, 403):
                    raise UcsUploadError("UCS authentication expired during UDB conversion.")
                result.raise_for_status()
                if len(result.content) > MAX_RESULT_BYTES:
                    raise UcsUploadError("UCS converted page is too large to analyze safely.")
                if not re.search(r"Uploaded\s+DB\s+type\s*:\s*ABS\b", result.text, re.I):
                    raise UcsUploadError("UCS did not confirm conversion to ABS.")
            conversion_seconds = time.perf_counter() - started_at - upload_seconds
            if not re.search(r"Tables\s*\(\s*\d+\s*\)", result.text, re.I):
                info_url, info_fields = discover_action_form(result.text, result_url, "showdbinfo")
                result, result_url = self._request("POST", info_url, data=info_fields,
                    headers={"Origin": UCS_ORIGIN, "Referer": result_url, "Accept": "text/html"})
                if result.status_code in (401, 403):
                    raise UcsUploadError("UCS authentication expired while reading DB info.")
                result.raise_for_status()
                if len(result.content) > MAX_RESULT_BYTES:
                    raise UcsUploadError("UCS DB-info page is too large to analyze safely.")
            analysis = parse_ucs_result(result.text)
            analysis["timings_seconds"] = {
                "upload": round(upload_seconds, 1),
                "conversion": round(conversion_seconds, 1),
                "db_info": round(time.perf_counter() - started_at - upload_seconds - conversion_seconds, 1),
            }
            reader = _ResultReader()
            reader.feed(result.text)
            valid_tables = {table["name"] for table in analysis["tables"]}
            self._table_urls = {}
            unresolved = []
            for label, href, onclick, attributes in reader.links:
                if label not in valid_tables:
                    continue
                if not href or href.startswith(('#', 'javascript:')):
                    unresolved.append({"name": label, "href": _safe_control(href),
                                       "onclick": _safe_control(onclick), "attributes": attributes})
                    continue
                target_url = urljoin(result_url, href)
                query = parse_qs(urlsplit(target_url).query)
                if (_ucs_url(target_url) and query.get("action") == ["showdbtable"]
                        and query.get("table") == [label] and query.get("linkfile")):
                    self._table_urls[label] = target_url
                else:
                    unresolved.append({"name": label, "href": _safe_control(href),
                                       "onclick": _safe_control(onclick), "attributes": attributes})
            analysis["source"] = "UCS result page"
            analysis["readable_tables"] = sorted(self._table_urls)
            analysis["unresolved_table_controls"] = unresolved
            analysis["table_data"] = self.fetch_all_tables(analysis["tables"]) if fetch_tables else {}
            analysis["loaded_table_count"] = sum("rows" in item for item in analysis["table_data"].values())
            analysis["complete_table_count"] = sum(item.get("complete", False) for item in analysis["table_data"].values())
            return analysis
        except requests.exceptions.SSLError as exc:
            raise UcsUploadError("UCS TLS certificate validation failed.") from exc
        except requests.exceptions.Timeout as exc:
            raise UcsUploadError("UCS did not respond before the timeout.") from exc
        except requests.exceptions.RequestException as exc:
            raise UcsUploadError("Could not connect to UCS. Check the network and try again.") from exc

    def fetch_table(self, name):
        if name not in self._table_urls:
            raise UcsUploadError("This table has no verified UCS link in the uploaded result.")
        try:
            response, _ = self._request("GET", self._table_urls[name], timeout=(10, 30))
            if response.status_code in (401, 403):
                raise UcsUploadError("UCS authentication expired. Upload the file again.")
            response.raise_for_status()
            if len(response.content) > MAX_RESULT_BYTES:
                raise UcsUploadError("UCS table page is too large to display safely.")
            return parse_ucs_table(response.text, name)
        except requests.exceptions.RequestException as exc:
            raise UcsUploadError("Could not load this table from UCS.") from exc

    def fork_for_table_reads(self):
        """Give each parallel read its own authenticated requests session."""
        session = requests.Session()
        session.auth = self.session.auth
        session.headers.update(self.session.headers)
        session.cookies.update(self.session.cookies)
        client = UcsClient(session=session, base_url=self.base_url)
        client._table_urls = dict(self._table_urls)
        return client

    def fetch_table_summary(self, name, expected):
        table = self.fetch_table(name)
        table["expected_rows"] = expected
        table["complete"] = not table["truncated"] and len(table["rows"]) >= expected
        if not table["complete"]:
            table["error"] = "UCS returned fewer rows than the summary, or the table exceeded the local limit."
        return table

    def fetch_all_tables(self, summaries):
        result = {}
        for summary in summaries:
            name, expected = summary["name"], summary["rows"]
            if name not in self._table_urls:
                result[name] = {"name": name, "expected_rows": expected, "complete": False,
                                "error": "UCS did not provide a direct table URL."}
                continue
            try:
                result[name] = self.fetch_table_summary(name, expected)
            except UcsUploadError as exc:
                result[name] = {"name": name, "expected_rows": expected, "complete": False,
                                "error": str(exc)}
        return result

    def close(self):
        self.session.auth = None
        self.session.close()
