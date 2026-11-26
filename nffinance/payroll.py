"""工资计算（纯函数，便于核对）。金额一律为「分」。

时薪两种自动算法（由月薪推算）：
  rough：时薪 = 月薪 ÷ (30 − 休息日) ÷ 每日工作小时
  at   ：奥地利会计法，每月工作 4,33 周 × 每周小时（40 小时/周 → 173,2 小时/月），时薪 = 月薪 ÷ 月工时

工资 = min(工时 × 时薪, 封顶月薪[0=不封顶]) + 加班费（手动输入，不受封顶限制）
"""
from decimal import Decimal, ROUND_HALF_UP

WEEKS_PER_MONTH = Decimal("4.33")


def de_num(x, nd=2) -> str:
    q = Decimal(1).scaleb(-nd)
    s = f"{Decimal(x).quantize(q, ROUND_HALF_UP):,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def hourly_from_salary(method, salary_cents, rest_days, daily_hours, weekly_hours):
    """返回 (时薪分, 算式文字)；参数不合法返回 None。时薪四舍五入到分。"""
    sal = Decimal(int(salary_cents)) / 100
    if sal <= 0:
        return None
    if method == "at":
        wh = Decimal(str(weekly_hours))
        month_hours = WEEKS_PER_MONTH * wh
        if month_hours <= 0:
            return None
        rate = sal / month_hours
        f = f"{de_num(sal)} ÷ (4,33 × {de_num(wh, 0 if wh == wh.to_integral() else 2)}) = {de_num(sal)} ÷ {de_num(month_hours)}"
    else:
        days = 30 - int(rest_days)
        dh = Decimal(str(daily_hours))
        if days <= 0 or dh <= 0:
            return None
        rate = sal / days / dh
        f = f"{de_num(sal)} ÷ (30 − {int(rest_days)}) ÷ {de_num(dh, 0 if dh == dh.to_integral() else 2)} = {de_num(sal)} ÷ {days} ÷ {de_num(dh, 0 if dh == dh.to_integral() else 2)}"
    cents = int((rate * 100).quantize(Decimal(1), ROUND_HALF_UP))
    return cents, f"{f} = {de_num(Decimal(cents) / 100)} €/h"


def entry_minutes(start: int, end: int, break_min: int) -> int:
    """下班早于上班视为跨午夜；返回实际工作分钟数（≤0 表示无效）。"""
    span = end - start if end >= start else end + 1440 - start
    return span - int(break_min)


def parse_hhmm(text: str):
    t = text.strip()
    if not t:
        return None
    try:
        if ":" in t:
            h, _, m = t.partition(":")
            h, m = int(h or 0), int(m or 0)
        elif len(t) <= 2:
            h, m = int(t), 0
        elif len(t) == 3:
            h, m = int(t[0]), int(t[1:])
        else:
            h, m = int(t[:2]), int(t[2:4])
    except ValueError:
        return None
    return h * 60 + m if h <= 23 and m <= 59 else None


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_hours(minutes: int) -> str:
    return f"{de_num(Decimal(minutes) / 60)} h"


def calc(worker, total_minutes: int, overtime_cents: int) -> dict:
    rate = int(worker["hourly"])
    cap = int(worker["cap"])
    gross = (total_minutes * rate + 30) // 60  # 工时×时薪，四舍五入到分
    capped = cap > 0 and gross > cap
    regular = cap if capped else gross
    return {
        "minutes": total_minutes, "rate": rate, "cap": cap, "gross": gross,
        "capped": capped, "regular": regular, "overtime": int(overtime_cents),
        "total": regular + int(overtime_cents),
    }


def month_result(db, worker, y: int, m: int) -> dict:
    """某工人某月的完整结算：工时 → 基本工资(封顶) → 加班 → 应付 → 实付(转账+现金)。"""
    wid = worker["id"]
    mo = db.get_month(wid, y, m)
    daily = sum(e["minutes"] for e in db.entries(wid, y, m))
    minutes = mo["total_minutes"] if mo["mode"] == "total" else daily
    mult = Decimal(str(worker["ot_mult"]))
    ot_calc = int((Decimal(mo["ot_minutes"]) * int(worker["hourly"]) * mult / 60).quantize(Decimal(1), ROUND_HALF_UP))
    extra = db.get_overtime(wid, y, m)
    r = calc(worker, minutes, ot_calc + extra)
    r.update(mode=mo["mode"], ot_minutes=mo["ot_minutes"], ot_mult=float(mult), ot_calc=ot_calc, ot_extra=extra,
             transfer=mo["transfer"], cash=mo["cash"], paid=mo["transfer"] + mo["cash"], daily_minutes=daily)
    return r


def carry_over(db, worker, y: int, m: int) -> int:
    """截至上月底仍未付清的工资（应付合计 − 实付合计）。"""
    prefix = f"{y}-{m:02d}"
    total = 0
    for ym in db.months_with_data(worker["id"]):
        if ym < prefix:
            r = month_result(db, worker, int(ym[:4]), int(ym[5:7]))
            total += r["total"] - r["paid"]
    return total


def month_rows(db, y: int, m: int, worker_ids=None):
    """[(worker, result)]：在职、或该月/之前有数据（含未付结转）的工人；result 含 carry / cum。"""
    out = []
    for w in db.workers():
        if worker_ids is not None and w["id"] not in worker_ids:
            continue
        r = month_result(db, w, y, m)
        r["carry"] = carry_over(db, w, y, m)
        r["cum"] = r["carry"] + r["total"] - r["paid"]
        if worker_ids is not None or w["active"] or r["total"] or r["paid"] or r["carry"]:
            out.append((w, r))
    return out


def payroll_expense(rows, basis: str) -> int:
    """工资计入支出：basis='payable' 按应付，'paid' 按实付。"""
    return sum(r["total"] if basis == "payable" else r["paid"] for _w, r in rows)
