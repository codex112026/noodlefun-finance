import os
from datetime import datetime, date as _date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import CHANNELS
from .i18n import fmt_eur
from .paths import resource_path

RED = colors.HexColor("#AB0D0C")
LIGHT = colors.HexColor("#F6E9E9")

_FONT = None


def _font() -> str:
    """优先使用 Windows 自带微软雅黑（含中文与德语变音符号），失败则退回内置 CID 字体。"""
    global _FONT
    if _FONT:
        return _FONT
    candidates = [
        (r"C:\Windows\Fonts\msyh.ttc", 0),
        (r"C:\Windows\Fonts\simsun.ttc", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None),
    ]
    for path, idx in candidates:
        if os.path.exists(path):
            try:
                f = TTFont("NFBody", path, subfontIndex=idx) if idx is not None else TTFont("NFBody", path)
                pdfmetrics.registerFont(f)
                _FONT = "NFBody"
                return _FONT
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _FONT = "STSong-Light"
    return _FONT


def _styles():
    f = _font()
    return {
        "title": ParagraphStyle("t", fontName=f, fontSize=18, leading=22, textColor=colors.white),
        "sub": ParagraphStyle("s", fontName=f, fontSize=10, leading=13, textColor=colors.white),
        "h": ParagraphStyle("h", fontName=f, fontSize=12, leading=16, textColor=RED, spaceBefore=10, spaceAfter=4),
        "cell": ParagraphStyle("c", fontName=f, fontSize=8.5, leading=11),
    }


def _header(title, subtitle, width, st):
    logo = Image(str(resource_path("assets/logo_banner.png")), width=5.2 * cm, height=5.2 * cm * 445 / 905)
    right = [Paragraph(title, st["title"]), Paragraph(subtitle, st["sub"])]
    t = Table([[logo, right]], colWidths=[5.6 * cm, width - 5.6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), RED),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _table(data, col_widths, num_cols=(), total_row=True, font=None):
    f = font or _font()
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), f),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), RED),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF5F5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for c in num_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    if total_row and len(data) > 2:
        style += [("BACKGROUND", (0, -1), (-1, -1), LIGHT), ("LINEABOVE", (0, -1), (-1, -1), 0.8, RED)]
    t.setStyle(TableStyle(style))
    return t


def _footer(tr):
    f = _font()

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(f, 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(1.5 * cm, 1 * cm, f"Noodle Fun · {tr('generated')}: {datetime.now():%d.%m.%Y %H:%M}")
        canvas.drawRightString(A4[0] - 1.5 * cm, 1 * cm, tr("page", n=doc.page))
        canvas.restoreState()

    return draw


def _sum_channels(rows):
    return {c: sum(r[c] for r in rows) for c in CHANNELS}


def _cat_totals(exps):
    out = {}
    for e in exps:
        out[e["category"]] = out.get(e["category"], 0) + e["amount"]
    return dict(sorted(out.items()))


def _summary_blocks(story, st, tr, ch_totals, cat_totals, width):
    income = sum(ch_totals.values())
    spent = sum(cat_totals.values())
    story.append(Paragraph(tr("by_channel"), st["h"]))
    data = [[tr("channel"), tr("amount")]] + [[tr(c), fmt_eur(ch_totals[c])] for c in CHANNELS]
    data.append([tr("total_income"), fmt_eur(income)])
    story.append(_table(data, [width * 0.6, width * 0.4], num_cols=(1,)))
    story.append(Paragraph(tr("by_category"), st["h"]))
    data = [[tr("category"), tr("amount")]] + [[k, fmt_eur(v)] for k, v in cat_totals.items()]
    if not cat_totals:
        data.append([tr("no_data"), ""])
    data.append([tr("total_expenses"), fmt_eur(spent)])
    story.append(_table(data, [width * 0.6, width * 0.4], num_cols=(1,)))
    story.append(Spacer(1, 8))
    bal = Table([[tr("balance"), fmt_eur(income - spent)]], colWidths=[width * 0.6, width * 0.4])
    bal.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _font()), ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.8, RED),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(bal)


def _exp_table(exps, st, tr, width):
    cell = st["cell"]
    data = [[tr("date"), tr("category"), tr("note"), tr("amount")]]
    for e in exps:
        d = _date.fromisoformat(e["date"]).strftime("%d.%m.%Y")
        data.append([d, Paragraph(e["category"], cell), Paragraph(e["note"] or "", cell), fmt_eur(e["amount"])])
    if not exps:
        return Paragraph(tr("no_data"), cell)
    data.append(["", "", tr("total"), fmt_eur(sum(e["amount"] for e in exps))])
    return _table(data, [2.2 * cm, 4 * cm, width - 2.2 * cm - 4 * cm - 3 * cm, 3 * cm], num_cols=(3,))


def build_daily(path, db, iso_date, tr):
    st = _styles()
    width = A4[0] - 3 * cm
    d = _date.fromisoformat(iso_date)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.8 * cm, title=f"{tr('report_daily')} {d:%d.%m.%Y}")
    story = [_header(tr("report_daily"), f"{d:%d.%m.%Y}", width, st), Spacer(1, 8)]
    rev = db.get_revenue(iso_date)
    ch = {c: (rev[c] if rev else 0) for c in CHANNELS}
    story.append(Paragraph(tr("tab_revenue"), st["h"]))
    data = [[tr("channel"), tr("amount")]] + [[tr(c), fmt_eur(ch[c])] for c in CHANNELS]
    data.append([tr("total_income"), fmt_eur(sum(ch.values()))])
    story.append(_table(data, [width * 0.6, width * 0.4], num_cols=(1,)))
    if rev and rev["note"]:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"{tr('note')}: {rev['note']}", st["cell"]))
    exps = db.expenses_on(iso_date)
    story.append(Paragraph(tr("expense_list"), st["h"]))
    story.append(_exp_table(exps, st, tr, width))
    story.append(Spacer(1, 10))
    bal = sum(ch.values()) - sum(e["amount"] for e in exps)
    t = Table([[tr("balance"), fmt_eur(bal)]], colWidths=[width * 0.6, width * 0.4])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _font()), ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.8, RED),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    foot = _footer(tr)
    doc.build(story, onFirstPage=foot, onLaterPages=foot)


def build_monthly(path, db, year, month, tr):
    st = _styles()
    width = A4[0] - 3 * cm
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.8 * cm, title=f"{tr('report_monthly')} {month:02d}/{year}")
    story = [_header(tr("report_monthly"), f"{month:02d} / {year}", width, st), Spacer(1, 8)]
    rows = db.revenues_in_month(year, month)
    exps = db.expenses_in_month(year, month)

    story.append(Paragraph(tr("daily_revenue_table"), st["h"]))
    if rows:
        head = [tr("date")] + [tr(c) for c in CHANNELS] + [tr("total")]
        data = [head]
        for r in rows:
            d = _date.fromisoformat(r["date"]).strftime("%d.%m.")
            data.append([d] + [fmt_eur(r[c]) for c in CHANNELS] + [fmt_eur(sum(r[c] for c in CHANNELS))])
        tot = _sum_channels(rows)
        data.append([tr("total")] + [fmt_eur(tot[c]) for c in CHANNELS] + [fmt_eur(sum(tot.values()))])
        cw = [1.5 * cm] + [(width - 1.5 * cm - 2.6 * cm) / 5] * 5 + [2.6 * cm]
        t = _table(data, cw, num_cols=range(1, 7))
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5)]))
        story.append(t)
    else:
        story.append(Paragraph(tr("no_data"), st["cell"]))

    story.append(Paragraph(tr("expense_list"), st["h"]))
    story.append(_exp_table(exps, st, tr, width))
    story.append(Paragraph(tr("summary"), st["h"]))
    _summary_blocks(story, st, tr, _sum_channels(rows), _cat_totals(exps), width)
    foot = _footer(tr)
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
