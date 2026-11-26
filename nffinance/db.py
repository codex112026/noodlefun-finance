import sqlite3
from datetime import date as _date
from pathlib import Path

from .paths import data_dir

CHANNELS = ["cash", "card", "lieferando", "foodora", "wolt"]


def month_range(year: int, month: int):
    start = _date(year, month, 1)
    end = _date(year + (month == 12), (month % 12) + 1, 1)
    return start.isoformat(), end.isoformat()  # [start, end)


class Database:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "finance.db"
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        # 数据库放在 OneDrive 等同步文件夹时，用单文件模式，避免 -wal/-shm 文件同步出错
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS revenue(
                date TEXT PRIMARY KEY,
                cash INTEGER NOT NULL DEFAULT 0,
                card INTEGER NOT NULL DEFAULT 0,
                lieferando INTEGER NOT NULL DEFAULT 0,
                foodora INTEGER NOT NULL DEFAULT 0,
                wolt INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS categories(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                amount INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_exp_date ON expenses(date);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS workers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                hourly INTEGER NOT NULL DEFAULT 0,       -- 时薪（分）
                cap INTEGER NOT NULL DEFAULT 0,          -- 封顶月薪（分），0=不封顶
                salary INTEGER NOT NULL DEFAULT 0,       -- 月薪（分），仅用于自动计算时薪
                method TEXT NOT NULL DEFAULT 'rough',    -- rough | at
                rest_days INTEGER NOT NULL DEFAULT 8,
                daily_hours REAL NOT NULL DEFAULT 8,
                weekly_hours REAL NOT NULL DEFAULT 40,
                ot_mult REAL NOT NULL DEFAULT 1.5,       -- 加班时间折算倍率
                active INTEGER NOT NULL DEFAULT 1        -- 1=在职 0=离职
            );
            CREATE TABLE IF NOT EXISTS work_entries(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                start INTEGER NOT NULL,                  -- 距 0:00 的分钟数
                end INTEGER NOT NULL,
                break_min INTEGER NOT NULL DEFAULT 0,
                minutes INTEGER NOT NULL                 -- 实际工作分钟数
            );
            CREATE INDEX IF NOT EXISTS idx_we ON work_entries(worker_id, date);
            CREATE TABLE IF NOT EXISTS payroll_months(
                worker_id INTEGER NOT NULL,
                ym TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'daily',      -- daily=按每日工时 | total=直接输入总工时
                total_minutes INTEGER NOT NULL DEFAULT 0,
                ot_minutes INTEGER NOT NULL DEFAULT 0,   -- 加班时间（分钟，另计）
                transfer INTEGER NOT NULL DEFAULT 0,     -- 转账金额（分）
                cash INTEGER NOT NULL DEFAULT 0,         -- 现金金额（分）
                PRIMARY KEY(worker_id, ym)
            );
            CREATE TABLE IF NOT EXISTS overtime(
                worker_id INTEGER NOT NULL,
                ym TEXT NOT NULL,                        -- 'YYYY-MM'
                amount INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(worker_id, ym)
            );
            """
        )
        # 旧版数据库升级：给 workers 补列
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(workers)")}
        if "ot_mult" not in cols:
            self.conn.execute("ALTER TABLE workers ADD COLUMN ot_mult REAL NOT NULL DEFAULT 1.5")
        if "active" not in cols:
            self.conn.execute("ALTER TABLE workers ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        self.conn.commit()

    # ---- 金额一律以「分」存储（整数），避免浮点误差 ----
    def save_revenue(self, d: str, cents: dict, note: str = ""):
        vals = [int(cents.get(c, 0)) for c in CHANNELS]
        self.conn.execute(
            "INSERT INTO revenue(date,cash,card,lieferando,foodora,wolt,note) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET cash=excluded.cash, card=excluded.card, "
            "lieferando=excluded.lieferando, foodora=excluded.foodora, wolt=excluded.wolt, note=excluded.note",
            [d, *vals, note],
        )
        self.conn.commit()

    def get_revenue(self, d: str):
        return self.conn.execute("SELECT * FROM revenue WHERE date=?", [d]).fetchone()

    def delete_revenue(self, d: str):
        self.conn.execute("DELETE FROM revenue WHERE date=?", [d])
        self.conn.commit()

    def revenues_in_month(self, y: int, m: int):
        s, e = month_range(y, m)
        return self.conn.execute(
            "SELECT * FROM revenue WHERE date>=? AND date<? ORDER BY date", [s, e]
        ).fetchall()

    # ---- 支出 ----
    def categories(self):
        return [r["name"] for r in self.conn.execute("SELECT name FROM categories ORDER BY name COLLATE NOCASE")]

    def add_category(self, name: str) -> bool:
        name = name.strip()
        if not name:
            return False
        try:
            self.conn.execute("INSERT INTO categories(name) VALUES(?)", [name])
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_category(self, name: str):
        # 只删除类别名；已有支出记录保留原类别文字
        self.conn.execute("DELETE FROM categories WHERE name=?", [name])
        self.conn.commit()

    def add_expense(self, d: str, category: str, cents: int, note: str = ""):
        self.conn.execute(
            "INSERT INTO expenses(date,category,amount,note) VALUES(?,?,?,?)", [d, category, int(cents), note]
        )
        self.conn.commit()

    def update_expense(self, exp_id: int, d: str, category: str, cents: int, note: str = ""):
        self.conn.execute(
            "UPDATE expenses SET date=?, category=?, amount=?, note=? WHERE id=?",
            [d, category, int(cents), note, exp_id],
        )
        self.conn.commit()

    def delete_expense(self, exp_id: int):
        self.conn.execute("DELETE FROM expenses WHERE id=?", [exp_id])
        self.conn.commit()

    def expenses_in_month(self, y: int, m: int):
        s, e = month_range(y, m)
        return self.conn.execute(
            "SELECT * FROM expenses WHERE date>=? AND date<? ORDER BY date, id", [s, e]
        ).fetchall()

    def expenses_on(self, d: str):
        return self.conn.execute("SELECT * FROM expenses WHERE date=? ORDER BY id", [d]).fetchall()

    # ---- 工资结算 ----
    def workers(self):
        return self.conn.execute("SELECT * FROM workers ORDER BY active DESC, name COLLATE NOCASE").fetchall()

    def get_worker(self, wid: int):
        return self.conn.execute("SELECT * FROM workers WHERE id=?", [wid]).fetchone()

    def save_worker(self, w: dict, wid=None):
        """新增（wid=None）或更新；姓名重复返回 None，否则返回 id。"""
        vals = [w["name"].strip(), int(w["hourly"]), int(w["cap"]), int(w["salary"]), w["method"],
                int(w["rest_days"]), float(w["daily_hours"]), float(w["weekly_hours"]),
                float(w.get("ot_mult", 1.5)), int(w.get("active", 1))]
        if not vals[0]:
            return None
        try:
            if wid is None:
                cur = self.conn.execute(
                    "INSERT INTO workers(name,hourly,cap,salary,method,rest_days,daily_hours,weekly_hours,"
                    "ot_mult,active) VALUES(?,?,?,?,?,?,?,?,?,?)", vals)
                wid = cur.lastrowid
            else:
                self.conn.execute(
                    "UPDATE workers SET name=?,hourly=?,cap=?,salary=?,method=?,rest_days=?,daily_hours=?,"
                    "weekly_hours=?,ot_mult=?,active=? WHERE id=?", vals + [wid])
            self.conn.commit()
            return wid
        except sqlite3.IntegrityError:
            return None

    def delete_worker(self, wid: int):
        self.conn.execute("DELETE FROM work_entries WHERE worker_id=?", [wid])
        self.conn.execute("DELETE FROM overtime WHERE worker_id=?", [wid])
        self.conn.execute("DELETE FROM payroll_months WHERE worker_id=?", [wid])
        self.conn.execute("DELETE FROM workers WHERE id=?", [wid])
        self.conn.commit()

    def add_entry(self, wid, d, start, end, break_min, minutes):
        self.conn.execute(
            "INSERT INTO work_entries(worker_id,date,start,end,break_min,minutes) VALUES(?,?,?,?,?,?)",
            [wid, d, start, end, break_min, minutes])
        self.conn.commit()

    def update_entry(self, eid, d, start, end, break_min, minutes):
        self.conn.execute(
            "UPDATE work_entries SET date=?,start=?,end=?,break_min=?,minutes=? WHERE id=?",
            [d, start, end, break_min, minutes, eid])
        self.conn.commit()

    def delete_entry(self, eid):
        self.conn.execute("DELETE FROM work_entries WHERE id=?", [eid])
        self.conn.commit()

    def entries(self, wid, y, m):
        s, e = month_range(y, m)
        return self.conn.execute(
            "SELECT * FROM work_entries WHERE worker_id=? AND date>=? AND date<? ORDER BY date, start, id",
            [wid, s, e]).fetchall()

    def get_overtime(self, wid, y, m) -> int:
        r = self.conn.execute("SELECT amount FROM overtime WHERE worker_id=? AND ym=?",
                              [wid, f"{y}-{m:02d}"]).fetchone()
        return r["amount"] if r else 0

    def set_overtime(self, wid, y, m, cents: int):
        self.conn.execute(
            "INSERT INTO overtime(worker_id,ym,amount) VALUES(?,?,?) "
            "ON CONFLICT(worker_id,ym) DO UPDATE SET amount=excluded.amount",
            [wid, f"{y}-{m:02d}", int(cents)])
        self.conn.commit()

    def get_month(self, wid, y, m) -> dict:
        r = self.conn.execute("SELECT * FROM payroll_months WHERE worker_id=? AND ym=?",
                              [wid, f"{y}-{m:02d}"]).fetchone()
        if r:
            return {k: r[k] for k in ("mode", "total_minutes", "ot_minutes", "transfer", "cash")}
        return {"mode": "daily", "total_minutes": 0, "ot_minutes": 0, "transfer": 0, "cash": 0}

    def set_month(self, wid, y, m, **fields):
        cur = self.get_month(wid, y, m)
        cur.update(fields)
        self.conn.execute(
            "INSERT INTO payroll_months(worker_id,ym,mode,total_minutes,ot_minutes,transfer,cash) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(worker_id,ym) DO UPDATE SET mode=excluded.mode, "
            "total_minutes=excluded.total_minutes, ot_minutes=excluded.ot_minutes, "
            "transfer=excluded.transfer, cash=excluded.cash",
            [wid, f"{y}-{m:02d}", cur["mode"], int(cur["total_minutes"]), int(cur["ot_minutes"]),
             int(cur["transfer"]), int(cur["cash"])])
        self.conn.commit()

    def months_with_data(self, wid) -> list:
        rows = self.conn.execute(
            "SELECT substr(date,1,7) ym FROM work_entries WHERE worker_id=? UNION "
            "SELECT ym FROM payroll_months WHERE worker_id=? UNION SELECT ym FROM overtime WHERE worker_id=?",
            [wid, wid, wid]).fetchall()
        return sorted(r["ym"] for r in rows)

    # ---- 设置 / 备份 ----
    def get_setting(self, key, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", [key]).fetchone()
        return r["value"] if r else default

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [key, str(value)],
        )
        self.conn.commit()

    def close(self):
        try:
            self.conn.commit()
            self.conn.close()
        except Exception:
            pass

    def backup_to(self, dest: str):
        out = sqlite3.connect(dest)
        with out:
            self.conn.backup(out)
        out.close()
