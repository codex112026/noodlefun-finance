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
            """
        )
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
