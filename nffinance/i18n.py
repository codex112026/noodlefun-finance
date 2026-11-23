LANGS = {"zh": "中文", "de": "Deutsch"}

_T = {
    "app_title": {"zh": "Noodle Fun 财务结算", "de": "Noodle Fun Buchhaltung"},
    "tab_revenue": {"zh": "每日营业额", "de": "Tagesumsatz"},
    "tab_expense": {"zh": "支出", "de": "Ausgaben"},
    "tab_summary": {"zh": "汇总与报表", "de": "Auswertung & Berichte"},
    "date": {"zh": "日期", "de": "Datum"},
    "cash": {"zh": "现金", "de": "Bargeld"},
    "card": {"zh": "刷卡", "de": "Karte"},
    "lieferando": {"zh": "Lieferando", "de": "Lieferando"},
    "foodora": {"zh": "foodora", "de": "foodora"},
    "wolt": {"zh": "wolt", "de": "wolt"},
    "total": {"zh": "合计", "de": "Summe"},
    "note": {"zh": "备注", "de": "Notiz"},
    "save": {"zh": "保存", "de": "Speichern"},
    "delete": {"zh": "删除", "de": "Löschen"},
    "saved": {"zh": "已保存", "de": "Gespeichert"},
    "confirm_delete": {"zh": "确定删除这条记录吗？", "de": "Diesen Eintrag wirklich löschen?"},
    "month_entries": {"zh": "本月记录（点击一行可载入修改）", "de": "Einträge dieses Monats (Zeile anklicken zum Bearbeiten)"},
    "category": {"zh": "类别", "de": "Kategorie"},
    "amount": {"zh": "金额", "de": "Betrag"},
    "add": {"zh": "添加", "de": "Hinzufügen"},
    "manage_categories": {"zh": "类别管理…", "de": "Kategorien verwalten…"},
    "new_category": {"zh": "新类别名称：", "de": "Name der neuen Kategorie:"},
    "category_exists": {"zh": "类别为空或已存在", "de": "Kategorie leer oder bereits vorhanden"},
    "need_category": {"zh": "请先在“类别管理”中添加类别", "de": "Bitte zuerst unter „Kategorien verwalten“ eine Kategorie anlegen"},
    "month": {"zh": "月份", "de": "Monat"},
    "income": {"zh": "收入", "de": "Einnahmen"},
    "expenses": {"zh": "支出", "de": "Ausgaben"},
    "balance": {"zh": "结余", "de": "Saldo"},
    "total_income": {"zh": "总收入", "de": "Gesamteinnahmen"},
    "total_expenses": {"zh": "总支出", "de": "Gesamtausgaben"},
    "channel": {"zh": "渠道", "de": "Kanal"},
    "by_category": {"zh": "按类别的支出", "de": "Ausgaben nach Kategorie"},
    "by_channel": {"zh": "按渠道的收入", "de": "Einnahmen nach Kanal"},
    "export_daily": {"zh": "导出日报 PDF", "de": "Tagesbericht als PDF"},
    "export_monthly": {"zh": "导出月报 PDF", "de": "Monatsbericht als PDF"},
    "pdf_saved": {"zh": "PDF 已保存：", "de": "PDF gespeichert: "},
    "pdf_open": {"zh": "是否现在打开？", "de": "Jetzt öffnen?"},
    "pdf_filter": {"zh": "PDF 文件 (*.pdf)", "de": "PDF-Dateien (*.pdf)"},
    "pdf_error": {"zh": "生成 PDF 失败：", "de": "PDF konnte nicht erstellt werden: "},
    "menu_file": {"zh": "文件", "de": "Datei"},
    "menu_language": {"zh": "语言", "de": "Sprache"},
    "menu_help": {"zh": "帮助", "de": "Hilfe"},
    "backup": {"zh": "备份数据库…", "de": "Datenbank sichern…"},
    "backup_done": {"zh": "备份已保存：", "de": "Sicherung gespeichert: "},
    "open_data_dir": {"zh": "打开数据文件夹", "de": "Datenordner öffnen"},
    "quit": {"zh": "退出", "de": "Beenden"},
    "check_update": {"zh": "检查更新…", "de": "Nach Updates suchen…"},
    "about": {"zh": "关于", "de": "Über"},
    "about_text": {"zh": "版本 {v}\n数据位置：{p}", "de": "Version {v}\nDatenspeicherort: {p}"},
    "update_available": {
        "zh": "发现新版本 {new}（当前 {cur}）。\n现在下载并安装吗？安装完成后软件会自动重启，数据不受影响。",
        "de": "Neue Version {new} verfügbar (aktuell {cur}).\nJetzt herunterladen und installieren? Die Anwendung startet danach neu, Ihre Daten bleiben erhalten.",
    },
    "update_none": {"zh": "已是最新版本。", "de": "Sie verwenden bereits die neueste Version."},
    "update_failed": {"zh": "检查更新失败：", "de": "Update-Prüfung fehlgeschlagen: "},
    "update_repo_unset": {
        "zh": "尚未配置 GitHub 仓库（nffinance/version.py 中的 GITHUB_REPO）。",
        "de": "GitHub-Repository ist nicht konfiguriert (GITHUB_REPO in nffinance/version.py).",
    },
    "downloading": {"zh": "正在下载更新…", "de": "Update wird heruntergeladen…"},
    "cancel": {"zh": "取消", "de": "Abbrechen"},
    "close": {"zh": "关闭", "de": "Schließen"},
    "no_data": {"zh": "（无记录）", "de": "(keine Einträge)"},
    "report_daily": {"zh": "日报", "de": "Tagesbericht"},
    "report_monthly": {"zh": "月报", "de": "Monatsbericht"},
    "daily_revenue_table": {"zh": "每日营业额", "de": "Tagesumsätze"},
    "expense_list": {"zh": "支出明细", "de": "Ausgabenliste"},
    "summary": {"zh": "汇总", "de": "Zusammenfassung"},
    "generated": {"zh": "生成时间", "de": "Erstellt am"},
    "page": {"zh": "第 {n} 页", "de": "Seite {n}"},
    "daily_report_date": {"zh": "日报日期", "de": "Datum des Tagesberichts"},
    "remove": {"zh": "删除所选", "de": "Auswahl löschen"},
    "new_name": {"zh": "新增", "de": "Neu"},
}


class Translator:
    def __init__(self, lang="zh"):
        self.lang = lang if lang in LANGS else "zh"

    def __call__(self, key, **kw):
        s = _T.get(key, {}).get(self.lang, key)
        return s.format(**kw) if kw else s


def fmt_eur(cents: int) -> str:
    """1234567 -> '12.345,67 €'（奥地利/德语格式）"""
    neg = cents < 0
    cents = abs(int(cents))
    s = f"{cents // 100:,}".replace(",", ".") + f",{cents % 100:02d}"
    return ("-" if neg else "") + s + " €"
