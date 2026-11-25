"""工资单 PDF：多人时第一页是全员汇总，之后每个工人一页（每日工时 + 计算过程）。"""
from datetime import date as _date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from . import payroll as P
from .i18n import fmt_eur
from .report import _footer, _header, _styles, _table


def _worker_story(w, entries, r, year, month, tr, st, width):
    story = [_header(tr("payroll_title"), f"{w['name']}  ·  {month:02d} / {year}", width, st), Spacer(1, 8)]
    story.append(Paragraph(tr("hours"), st["h"]))
    if entries:
        data = [[tr("date"), tr("start_time"), tr("end_time"), tr("break_min"), tr("hours")]]
        for e in entries:
            data.append([
                _date.fromisoformat(e["date"]).strftime("%d.%m.%Y"), P.fmt_hhmm(e["start"]), P.fmt_hhmm(e["end"]),
                str(e["break_min"]), P.fmt_hours(e["minutes"]),
            ])
        data.append([tr("total"), "", "", "", P.fmt_hours(r["minutes"])])
        story.append(_table(data, [width * 0.28, width * 0.18, width * 0.18, width * 0.16, width * 0.20],
                            num_cols=(1, 2, 3, 4)))
    else:
        story.append(Paragraph(tr("no_data"), st["cell"]))
    story.append(Spacer(1, 10))
    rows = [
        [tr("total_hours"), P.fmt_hours(r["minutes"])],
        [tr("hourly_rate"), fmt_eur(r["rate"]) + " / h"],
        [tr("regular_pay"), fmt_eur(r["gross"])],
    ]
    if r["capped"]:
        rows.append([tr("cap_applied", c=fmt_eur(r["cap"]), g=fmt_eur(r["gross"])), fmt_eur(r["cap"])])
    rows += [[tr("overtime_pay"), fmt_eur(r["overtime"])], [tr("total_pay"), fmt_eur(r["total"])]]
    story.append(_table([[tr("summary"), tr("amount")]] + rows, [width * 0.68, width * 0.32], num_cols=(1,)))
    return story


def build_payroll(path, db, year, month, tr, worker_ids=None):
    st = _styles()
    width = A4[0] - 3 * cm
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.8 * cm, title=f"{tr('payroll_title')} {month:02d}/{year}")
    workers = [w for w in db.workers() if worker_ids is None or w["id"] in worker_ids]
    results = []
    for w in workers:
        entries = db.entries(w["id"], year, month)
        r = P.calc(w, sum(e["minutes"] for e in entries), db.get_overtime(w["id"], year, month))
        results.append((w, entries, r))

    story = []
    if len(results) != 1:  # 全员汇总（只导出一人时省略）
        story += [_header(tr("payroll_summary"), f"{month:02d} / {year}", width, st), Spacer(1, 8)]
        if results:
            data = [[tr("worker"), tr("hours"), tr("hourly_short"), tr("sum_regular"), tr("sum_overtime"), tr("sum_total")]]
            for w, _e, r in results:
                data.append([Paragraph(w["name"], st["cell"]), P.fmt_hours(r["minutes"]), fmt_eur(r["rate"]),
                             fmt_eur(r["regular"]), fmt_eur(r["overtime"]), fmt_eur(r["total"])])
            data.append([tr("total"), P.fmt_hours(sum(r["minutes"] for _w, _e, r in results)), "",
                         fmt_eur(sum(r["regular"] for _w, _e, r in results)),
                         fmt_eur(sum(r["overtime"] for _w, _e, r in results)),
                         fmt_eur(sum(r["total"] for _w, _e, r in results))])
            story.append(_table(data, [width * 0.22, width * 0.15, width * 0.14, width * 0.17, width * 0.14,
                                       width * 0.18], num_cols=(1, 2, 3, 4, 5)))
        else:
            story.append(Paragraph(tr("no_workers"), st["cell"]))
    for i, (w, entries, r) in enumerate(results):
        if story:
            story.append(PageBreak())
        story += _worker_story(w, entries, r, year, month, tr, st, width)
    foot = _footer(tr)
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
