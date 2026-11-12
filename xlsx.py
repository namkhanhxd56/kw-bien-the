"""Ghi file .xlsx bằng thư viện chuẩn (zipfile + XML), không cần openpyxl — Railway chỉ chạy stdlib.

Đủ cho file xuất bộ keyword: nhiều sheet, chữ / số, dòng tiêu đề đậm, tô màu cả dòng, độ rộng cột,
cố định dòng đầu, bộ lọc ở dòng tiêu đề.

    wb = Sach()
    s = wb.sheet("Product", cot=[("Keyword", 48), ("SV", 10)])
    s.dong(["red truck", 1200], to="xanh")
    data = wb.bytes()
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

# Kiểu ô (thứ tự khớp cellXfs bên dưới): 0 thường · 1 tiêu đề · 2..n tô nền theo tên
_MAU = {"xanh": "FFDCE6F1", "vang": "FFFFF2CC", "xam": "FFEDEDED", "cam": "FFFBE4D5", "luc": "FFE2EFDA"}
_TO = {ten: i + 2 for i, ten in enumerate(_MAU)}
_KHONG_HOP_LE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_CAM_TEN = re.compile(r"[\[\]:*?/\\]")


def _cot(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class Sheet:
    def __init__(self, ten: str, cot: list[tuple[str, float]]):
        self.ten, self.cot = ten, cot
        self.rows: list[tuple[list, int]] = [([c for c, _ in cot], 1)]

    def dong(self, values: list, to: str | None = None, dam: bool = False) -> None:
        self.rows.append((list(values), 1 if dam else _TO.get(to, 0)))

    def _xml(self) -> str:
        ncot = len(self.cot)
        cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, (_, w) in enumerate(self.cot))
        out = []
        for r, (vals, st) in enumerate(self.rows, 1):
            cells = []
            for c, v in enumerate(vals):
                ref = f"{_cot(c)}{r}"
                s = f' s="{st}"' if st else ""
                if v is None or v == "":
                    if st:
                        cells.append(f'<c r="{ref}"{s}/>')
                elif isinstance(v, bool):
                    cells.append(f'<c r="{ref}"{s} t="b"><v>{int(v)}</v></c>')
                elif isinstance(v, (int, float)):
                    cells.append(f'<c r="{ref}"{s}><v>{v}</v></c>')
                else:
                    t = escape(_KHONG_HOP_LE.sub("", str(v)))
                    cells.append(f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{t}</t></is></c>')
            if st:   # tô hết bề ngang bảng, kể cả ô trống cuối dòng
                for c in range(len(vals), ncot):
                    cells.append(f'<c r="{_cot(c)}{r}" s="{st}"/>')
            out.append(f'<row r="{r}">{"".join(cells)}</row>')
        cuoi = f"{_cot(ncot - 1)}{len(self.rows)}"
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                '</sheetView></sheetViews>'
                f'<cols>{cols}</cols><sheetData>{"".join(out)}</sheetData>'
                f'<autoFilter ref="A1:{cuoi}"/></worksheet>')


class Sach:
    def __init__(self):
        self.sheets: list[Sheet] = []

    def sheet(self, ten: str, cot: list[tuple[str, float]]) -> Sheet:
        ten = _CAM_TEN.sub("-", ten)[:31] or "Sheet"
        co = {s.ten.lower() for s in self.sheets}
        goc, i = ten, 2
        while ten.lower() in co:
            ten = f"{goc[:28]} {i}"
            i += 1
        s = Sheet(ten, cot)
        self.sheets.append(s)
        return s

    def bytes(self) -> bytes:
        fills = '<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        fills += '<fill><patternFill patternType="solid"><fgColor rgb="FF1F3864"/></patternFill></fill>'
        fills += "".join(f'<fill><patternFill patternType="solid"><fgColor rgb="{m}"/></patternFill></fill>' for m in _MAU.values())
        xfs = ('<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
               '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>')
        xfs += "".join(f'<xf numFmtId="0" fontId="0" fillId="{i + 3}" borderId="0" xfId="0" applyFill="1"/>' for i in range(len(_MAU)))
        styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                  '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                  '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
                  f'<fills count="{3 + len(_MAU)}">{fills}</fills>'
                  '<borders count="1"><border/></borders>'
                  '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                  f'<cellXfs count="{2 + len(_MAU)}">{xfs}</cellXfs>'
                  '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        n = len(self.sheets)
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
              + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                        for i in range(1, n + 1)) + "</Types>")
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/></Relationships>')
        wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
              + "".join(f'<sheet name="{escape(s.ten, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                        for i, s in enumerate(self.sheets, 1)) + "</sheets><definedNames>"
              + "".join(f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
                        f"'{escape(s.ten).replace(chr(39), chr(39) * 2)}'!$A$1:${_cot(len(s.cot) - 1)}${len(s.rows)}</definedName>"
                        for i, s in enumerate(self.sheets)) + "</definedNames></workbook>")
        wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                             f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
                   + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                   'Target="styles.xml"/></Relationships>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", rels)
            z.writestr("xl/workbook.xml", wb)
            z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
            z.writestr("xl/styles.xml", styles)
            for i, s in enumerate(self.sheets, 1):
                z.writestr(f"xl/worksheets/sheet{i}.xml", s._xml())
        return buf.getvalue()
