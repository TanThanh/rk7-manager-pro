# rk7_pro/components/code_highlighter.py
import re
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import Qt

class UniversalScriptHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, lang="SQL"):
        super().__init__(parent)
        self.lang = lang.upper()
        self.rules = []
        self._build_rules()

    def set_language(self, lang: str):
        self.lang = lang.upper()
        self.rules.clear()
        self._build_rules()
        self.rehighlight()

    def _build_rules(self):
        # Common text formats
        keyword_fmt = QTextCharFormat()
        keyword_fmt.setForeground(QColor("#89B4FA"))  # Soft Sky Blue
        keyword_fmt.setFontWeight(QFont.Weight.Bold)

        func_fmt = QTextCharFormat()
        func_fmt.setForeground(QColor("#F9E2AF"))  # Soft Yellow
        func_fmt.setFontWeight(QFont.Weight.Medium)

        string_fmt = QTextCharFormat()
        string_fmt.setForeground(QColor("#A6E3A1"))  # Soft Green

        number_fmt = QTextCharFormat()
        number_fmt.setForeground(QColor("#FAB387"))  # Orange / Peach

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6C7086"))  # Muted Slate
        comment_fmt.setFontItalic(True)

        var_fmt = QTextCharFormat()
        var_fmt.setForeground(QColor("#F38BA8"))  # Red / Coral

        # Numbers
        self.rules.append((r"\b\d+(\.\d+)?\b", number_fmt))

        if self.lang == "SQL":
            sql_keywords = [
                "SELECT", "FROM", "WHERE", "INSERT", "INTO", "UPDATE", "DELETE",
                "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS",
                "ON", "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "TOP",
                "UNION", "ALL", "DISTINCT", "AS", "AND", "OR", "NOT", "IN", "IS",
                "NULL", "LIKE", "BETWEEN", "EXISTS", "CASE", "WHEN", "THEN", "ELSE",
                "END", "CREATE", "ALTER", "DROP", "TABLE", "VIEW", "INDEX", "PROCEDURE",
                "FUNCTION", "TRIGGER", "DATABASE", "SCHEMA", "BEGIN", "TRANSACTION",
                "COMMIT", "ROLLBACK", "DECLARE", "SET", "EXEC", "EXECUTE", "WITH"
            ]
            for kw in sql_keywords:
                self.rules.append((rf"\b{kw}\b", keyword_fmt))
                self.rules.append((rf"\b{kw.lower()}\b", keyword_fmt))

            sql_functions = [
                "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "ISNULL",
                "CONVERT", "CAST", "GETDATE", "DATEADD", "DATEDIFF", "SUBSTRING",
                "CHARINDEX", "LEN", "UPPER", "LOWER", "ROW_NUMBER", "RANK", "DENSE_RANK"
            ]
            for fn in sql_functions:
                self.rules.append((rf"\b{fn}\b", func_fmt))
                self.rules.append((rf"\b{fn.lower()}\b", func_fmt))

            # String literals: 'string'
            self.rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_fmt))
            # Comments: -- comment
            self.rules.append((r"--[^\n]*", comment_fmt))
            # Multi-line / inline comment: /* comment */
            self.rules.append((r"/\*.*?\*/", comment_fmt))

        elif self.lang in ("PYTHON", "PY"):
            py_keywords = [
                "def", "class", "import", "from", "as", "return", "if", "elif", "else",
                "for", "while", "break", "continue", "try", "except", "finally", "with",
                "lambda", "yield", "pass", "raise", "assert", "global", "nonlocal",
                "True", "False", "None", "async", "await"
            ]
            for kw in py_keywords:
                self.rules.append((rf"\b{kw}\b", keyword_fmt))

            self.rules.append((r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)", func_fmt))
            self.rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', string_fmt))
            self.rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_fmt))
            self.rules.append((r"#[^\n]*", comment_fmt))

        elif self.lang in ("BATCH", "CMD"):
            bat_keywords = [
                "echo", "off", "on", "set", "if", "else", "goto", "call", "pause",
                "exit", "for", "in", "do", "shift", "rem", "cd", "del", "copy",
                "xcopy", "robocopy", "mkdir", "md", "rmdir", "rd", "start"
            ]
            for kw in bat_keywords:
                self.rules.append((rf"\b{kw}\b", keyword_fmt))
                self.rules.append((rf"\b{kw.upper()}\b", keyword_fmt))

            # Variables %VAR%
            self.rules.append((r"%[a-zA-Z0-9_~:\]+%", var_fmt))
            self.rules.append((r"::[^\n]*", comment_fmt))
            self.rules.append((r"\brem\b[^\n]*", comment_fmt))

        elif self.lang in ("POWERSHELL", "PS1"):
            ps_keywords = [
                "function", "param", "if", "else", "elseif", "foreach", "for", "while",
                "switch", "return", "try", "catch", "finally", "throw", "trap", "break",
                "continue", "Get-", "Set-", "New-", "Remove-", "Start-", "Stop-"
            ]
            for kw in ps_keywords:
                self.rules.append((rf"\b{kw}[a-zA-Z0-9_-]*\b", keyword_fmt))

            self.rules.append((r"\$[a-zA-Z0-9_:]+", var_fmt))
            self.rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', string_fmt))
            self.rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_fmt))
            self.rules.append((r"#[^\n]*", comment_fmt))

        else:
            # Generic highlighter for txt, ini, sh, json
            self.rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', string_fmt))
            self.rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_fmt))
            self.rules.append((r"#[^\n]*", comment_fmt))
            self.rules.append((r"//[^\n]*", comment_fmt))
            self.rules.append((r";[^\n]*", comment_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)
