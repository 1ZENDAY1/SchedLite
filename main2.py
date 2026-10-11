import sqlite3
import sys
import json
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox


WEEKDAYS_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]

NOT_SELECTED = "— не выбрано —"

MAX_LESSON = 8


# ==================== ЦВЕТОВЫЕ ПАЛИТРЫ ====================

LIGHT = {
    "bg": "#f0f0f0",
    "fg": "#000000",
    "field_bg": "#ffffff",
    "field_fg": "#000000",
    "select_bg": "#0078d7",
    "select_fg": "#ffffff",
    "output_bg": "#f7f7f7",
    "output_fg": "#000000",
    "button_bg": "#e1e1e1",
    "button_fg": "#000000",
    "button_active": "#d0d0d0",
    "tab_bg": "#dcdcdc",
    "tab_selected": "#f0f0f0",
    "tab_fg": "#000000",
    "break_bg": "#eef4fa",
}

DARK = {
    "bg": "#2b2b2b",
    "fg": "#e0e0e0",
    "field_bg": "#3c3f41",
    "field_fg": "#e0e0e0",
    "select_bg": "#4a6a8a",
    "select_fg": "#ffffff",
    "output_bg": "#1e1e1e",
    "output_fg": "#e0e0e0",
    "button_bg": "#3c3f41",
    "button_fg": "#e0e0e0",
    "button_active": "#4a4a4a",
    "tab_bg": "#252525",
    "tab_selected": "#2b2b2b",
    "tab_fg": "#e0e0e0",
    "break_bg": "#333a44",
}


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


DB_PATH = get_base_dir() / "schedule.db"
SETTINGS_PATH = get_base_dir() / "settings.json"


# ==================== НАСТРОЙКИ ====================


def load_settings():
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def save_settings(data):
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


# ==================== БАЗА ДАННЫХ ====================


def db_connect():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Не найден файл базы данных:\n{DB_PATH}\n\n"
            f"Запусти init_db.py, чтобы создать его."
        )
    return sqlite3.connect(DB_PATH)


def load_classes():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT class_name FROM classes ORDER BY CAST(grade AS INTEGER), class_name"
        )
        return [row[0] for row in cur.fetchall()]


def load_lesson_times():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT lesson_number, start_time, end_time FROM lesson_times")
        return {n: (s, e) for n, s, e in cur.fetchall()}


def load_days():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT day_of_week FROM schedule")
        found = {row[0] for row in cur.fetchall()}
    return [d for d in WEEKDAYS_RU if d in found]


def get_letters_for_grade(grade):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT class_name FROM classes WHERE grade = ? ORDER BY class_name",
            (grade,),
        )
        letters = []
        for (name,) in cur.fetchall():
            letter = name[len(grade) :]
            if letter and letter not in letters:
                letters.append(letter)
        return letters


def _split_cabinets(raw):
    return [p.strip() for p in raw.split("/") if p.strip()]


def get_all_cabinets():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT cabinet FROM schedule")
        result = set()
        for (cab,) in cur.fetchall():
            result.update(_split_cabinets(cab))
        return sorted(result)


def get_busy_cabinets(day, lesson):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT cabinet FROM schedule "
            "WHERE day_of_week = ? AND lesson_number = ?",
            (day, lesson),
        )
        result = set()
        for (cab,) in cur.fetchall():
            result.update(_split_cabinets(cab))
        return result


# ==================== ФОРМИРОВАНИЕ ТЕКСТА ====================


def format_lesson_row(lesson_number, times, lesson, cabinet, mark=""):
    start, end = times.get(lesson_number, ("--:--", "--:--"))
    return f"  {lesson_number}. {start}–{end}  {lesson}  (каб. {cabinet}){mark}"


def get_lesson_status():
    times = load_lesson_times()
    now = datetime.now().strftime("%H:%M")
    current = next_lesson = None
    for n in sorted(times):
        s, e = times[n]
        if s <= now <= e:
            current = n
        elif now < s and next_lesson is None:
            next_lesson = n
    return current, next_lesson


def build_output(class_filter, day_filter, lesson_filter, highlight=False):
    if not class_filter:
        return "Выберите класс."

    conn = db_connect()
    cur = conn.cursor()

    if len(class_filter) > 1 and class_filter[-1].isalpha():
        classes = [class_filter]
    else:
        cur.execute(
            "SELECT class_name FROM classes WHERE grade = ? "
            "ORDER BY CAST(grade AS INTEGER), class_name",
            (class_filter,),
        )
        classes = [row[0] for row in cur.fetchall()]

    if not classes:
        conn.close()
        return f"Класс «{class_filter}» не найден в базе."

    times = load_lesson_times()

    if day_filter:
        days = [day_filter]
    else:
        cur.execute(
            "SELECT DISTINCT day_of_week FROM schedule WHERE class_name IN "
            f"({','.join('?' * len(classes))})",
            classes,
        )
        found = {row[0] for row in cur.fetchall()}
        days = [d for d in WEEKDAYS_RU if d in found]

    if not days:
        conn.close()
        return "Для выбранного класса расписание пока не заполнено."

    current_n, next_n = get_lesson_status() if highlight else (None, None)

    lines = []
    for cls in classes:
        lines.append(f"{cls}:")
        for day in days:
            lines.append(f"  {day}:")

            query = (
                "SELECT lesson_number, lesson, cabinet FROM schedule "
                "WHERE class_name = ? AND day_of_week = ?"
            )
            params = [cls, day]
            if lesson_filter is not None:
                query += " AND lesson_number = ?"
                params.append(lesson_filter)
            query += " ORDER BY lesson_number"

            cur.execute(query, params)
            rows = cur.fetchall()

            if not rows:
                lines.append("    (нет данных)")
            else:
                for n, lesson, cabinet in rows:
                    mark = ""
                    if highlight and day == WEEKDAYS_RU[datetime.now().weekday()]:
                        if n == current_n:
                            mark = "   ← идёт сейчас"
                        elif n == next_n:
                            mark = "   ← следующий"
                    lines.append(format_lesson_row(n, times, lesson, cabinet, mark))
            lines.append("")
        lines.append("")

    conn.close()
    return "\n".join(lines).rstrip()


def _minutes_between(start, end):
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    return (h2 * 60 + m2) - (h1 * 60 + m1)


# ==================== ПРИЛОЖЕНИЕ ====================


class SchedLiteApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SchedLite — электронное расписание")
        self.root.geometry("920x680")
        self.root.minsize(800, 580)

        self.settings = load_settings()
        self.theme = self.settings.get("theme", "light")

        try:
            self.classes = load_classes()
            self.days = load_days()
            self.times = load_lesson_times()
            self.all_cabinets = get_all_cabinets()
        except FileNotFoundError as e:
            messagebox.showerror("Ошибка", str(e))
            root.destroy()
            return

        self.bottom_bar = ttk.Frame(root, padding=(8, 4))
        self.bottom_bar.pack(side="bottom", fill="x")

        self.theme_btn = ttk.Button(
            self.bottom_bar,
            text="🌙 Тёмная тема",
            command=self.toggle_theme,
        )
        self.theme_btn.pack(side="right")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        self._build_schedule_tab()
        self._build_my_class_tab()
        self._build_bells_tab()
        self._build_cabinets_tab()

        self._apply_theme()
        self._tick()

    # ---------- Тема ----------

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.settings["theme"] = self.theme
        save_settings(self.settings)
        self._apply_theme()

    def _apply_theme(self):
        p = DARK if self.theme == "dark" else LIGHT
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg=p["bg"])

        style.configure("TFrame", background=p["bg"])
        style.configure("TLabel", background=p["bg"], foreground=p["fg"])

        style.configure(
            "TButton",
            background=p["button_bg"],
            foreground=p["button_fg"],
            borderwidth=1,
            focusthickness=0,
            padding=(8, 4),
        )
        style.map(
            "TButton",
            background=[("active", p["button_active"])],
            foreground=[("active", p["button_fg"])],
        )

        # --- Вкладки ---
        style.configure(
            "TNotebook",
            background=p["bg"],
            borderwidth=0,
            tabmargins=(4, 4, 4, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=p["tab_bg"],
            foreground=p["fg"],
            padding=(10, 4),
            borderwidth=0,
            focuscolor=p["bg"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", p["tab_selected"])],
            foreground=[("selected", p["tab_fg"])],
            expand=[("selected", (0, 0, 0, 0))],
            padding=[("selected", (10, 4)), ("!selected", (10, 4))],
        )

        style.configure(
            "TCombobox",
            fieldbackground=p["field_bg"],
            background=p["button_bg"],
            foreground=p["field_fg"],
            arrowcolor=p["fg"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", p["field_bg"])],
            foreground=[("readonly", p["field_fg"])],
        )

        style.configure(
            "Treeview",
            background=p["field_bg"],
            fieldbackground=p["field_bg"],
            foreground=p["field_fg"],
        )
        style.configure(
            "Treeview.Heading",
            background=p["button_bg"],
            foreground=p["button_fg"],
        )
        style.map(
            "Treeview",
            background=[("selected", p["select_bg"])],
            foreground=[("selected", p["select_fg"])],
        )

        for w in (self.schedule_output, self.today_output, self.cab_output):
            w.config(
                bg=p["output_bg"],
                fg=p["output_fg"],
                insertbackground=p["fg"],
            )

        if hasattr(self, "bells_table"):
            self.bells_table.tag_configure("break", background=p["break_bg"])

        if self.theme == "dark":
            self.theme_btn.config(text="☀ Светлая тема")
        else:
            self.theme_btn.config(text="🌙 Тёмная тема")

    # ---------- Вкладка «Расписание» ----------

    def _build_schedule_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Расписание")

        top = ttk.Frame(tab)
        top.pack(fill="x")

        ttk.Label(top, text="Параллель:").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.grade_var = tk.StringVar()
        grades = sorted({c[: len(c) - 1] for c in self.classes}, key=int)
        self.grade_box = ttk.Combobox(
            top,
            textvariable=self.grade_var,
            values=[NOT_SELECTED] + grades,
            state="readonly",
            width=14,
        )
        self.grade_box.set(NOT_SELECTED)
        self.grade_box.grid(row=0, column=1, padx=(0, 16))
        self.grade_box.bind("<<ComboboxSelected>>", self.on_grade_change)

        ttk.Label(top, text="Класс:").grid(row=0, column=2, padx=(0, 6), sticky="w")
        self.class_var = tk.StringVar()
        self.class_box = ttk.Combobox(
            top,
            textvariable=self.class_var,
            values=[NOT_SELECTED],
            state="readonly",
            width=14,
        )
        self.class_box.set(NOT_SELECTED)
        self.class_box.grid(row=0, column=3, padx=(0, 16))

        ttk.Label(top, text="День:").grid(row=0, column=4, padx=(0, 6), sticky="w")
        self.day_var = tk.StringVar()
        self.day_box = ttk.Combobox(
            top,
            textvariable=self.day_var,
            values=[NOT_SELECTED] + self.days,
            state="readonly",
            width=18,
        )
        self.day_box.set(NOT_SELECTED)
        self.day_box.grid(row=0, column=5, padx=(0, 16))

        ttk.Label(top, text="Урок:").grid(row=0, column=6, padx=(0, 6), sticky="w")
        self.lesson_var = tk.StringVar()
        self.lesson_box = ttk.Combobox(
            top,
            textvariable=self.lesson_var,
            values=[NOT_SELECTED] + [str(i) for i in range(1, MAX_LESSON + 1)],
            state="readonly",
            width=12,
        )
        self.lesson_box.set(NOT_SELECTED)
        self.lesson_box.grid(row=0, column=7)

        btns = ttk.Frame(tab, padding=(0, 10, 0, 10))
        btns.pack(fill="x")

        ttk.Button(
            btns,
            text="Показать расписание",
            command=self.on_show_schedule,
        ).pack(side="left")
        ttk.Button(
            btns,
            text="Мой класс",
            command=self.on_my_class,
        ).pack(side="left", padx=8)
        ttk.Button(
            btns,
            text="Очистить",
            command=self.on_clear_schedule,
        ).pack(side="left")

        self.schedule_output = self._make_output_area(tab)

    def on_grade_change(self, event=None):
        grade = self.grade_var.get()
        if grade == NOT_SELECTED:
            self.class_box["values"] = [NOT_SELECTED]
            self.class_var.set(NOT_SELECTED)
            return
        letters = get_letters_for_grade(grade)
        self.class_box["values"] = [NOT_SELECTED] + letters
        self.class_var.set(NOT_SELECTED)

    def on_show_schedule(self):
        grade = self.grade_var.get()
        letter = self.class_var.get()

        if grade == NOT_SELECTED:
            self._set_output(self.schedule_output, "Выберите параллель.")
            return

        if letter == NOT_SELECTED:
            class_filter = grade
        else:
            class_filter = grade + letter

        day_raw = self.day_var.get()
        day = None if day_raw == NOT_SELECTED else day_raw

        lesson_raw = self.lesson_var.get()
        lesson = None if lesson_raw == NOT_SELECTED else int(lesson_raw)

        text = build_output(class_filter, day, lesson)
        self._set_output(self.schedule_output, text)

    def on_my_class(self):
        my = self.settings.get("my_class")
        if not my:
            self._ask_my_class()
            my = self.settings.get("my_class")
        if not my:
            return

        grade = "".join(ch for ch in my if ch.isdigit())
        letter = "".join(ch for ch in my if ch.isalpha())
        self.grade_var.set(grade)
        self.on_grade_change()
        self.class_var.set(letter)
        self.on_show_schedule()

    def _ask_my_class(self):
        win = tk.Toplevel(self.root)
        win.title("Мой класс")
        win.geometry("300x180")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="Выберите свой класс:").pack(pady=(16, 6))
        var = tk.StringVar(value=self.settings.get("my_class", ""))
        box = ttk.Combobox(
            win,
            textvariable=var,
            values=self.classes,
            state="readonly",
            width=18,
        )
        box.pack()

        def ok():
            if var.get():
                self.settings["my_class"] = var.get()
                save_settings(self.settings)
                self._refresh_my_class()
            win.destroy()

        ttk.Button(win, text="Сохранить", command=ok).pack(pady=10)

    def on_clear_schedule(self):
        self.grade_var.set(NOT_SELECTED)
        self.on_grade_change()
        self.day_box.set(NOT_SELECTED)
        self.lesson_box.set(NOT_SELECTED)
        self._set_output(self.schedule_output, "")

    # ---------- Вкладка «Мой класс» ----------

    def _build_my_class_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Мой класс")

        header = ttk.Frame(tab)
        header.pack(fill="x")

        self.today_label = ttk.Label(header, text="", font=("Segoe UI", 11, "bold"))
        self.today_label.pack(side="left")

        ttk.Button(
            header,
            text="Сменить мой класс",
            command=self._ask_my_class,
        ).pack(side="right")

        self.today_output = self._make_output_area(tab)
        self._refresh_my_class()

    def _refresh_my_class(self):
        now = datetime.now()
        day_name = WEEKDAYS_RU[now.weekday()]
        my = self.settings.get("my_class")

        header = f"{now.strftime('%d.%m.%Y %H:%M')}  •  {day_name}"
        if my:
            header += f"  •  Мой класс: {my}"
        self.today_label.config(text=header)

        if not my:
            self._set_output(
                self.today_output,
                "Свой класс ещё не выбран.\n\n"
                "Нажми «Сменить мой класс» — и здесь будет "
                "расписание на сегодня с подсветкой текущего урока.",
            )
            return

        text = build_output(my, day_name, None, highlight=True)
        if "нет данных" in text or "не заполнено" in text:
            text = f"{my}\n  {day_name}:\n    (нет уроков или расписание не заполнено)"
        self._set_output(self.today_output, text)

    def _tick(self):
        self._refresh_my_class()
        self.root.after(30_000, self._tick)

    # ---------- Вкладка «Звонки» ----------

    def _build_bells_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Звонки")

        ttk.Label(
            tab,
            text="Расписание звонков",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self.bells_table = ttk.Treeview(
            tab,
            columns=("label", "start", "end", "dur"),
            show="headings",
            height=min(len(self.times) * 2, 20),
        )
        self.bells_table.heading("label", text="Событие")
        self.bells_table.heading("start", text="Начало")
        self.bells_table.heading("end", text="Конец")
        self.bells_table.heading("dur", text="Длительность")
        self.bells_table.column("label", width=160, anchor="center")
        self.bells_table.column("start", width=110, anchor="center")
        self.bells_table.column("end", width=110, anchor="center")
        self.bells_table.column("dur", width=140, anchor="center")

        sorted_nums = sorted(self.times)
        for i, n in enumerate(sorted_nums):
            s, e = self.times[n]
            self.bells_table.insert(
                "",
                "end",
                values=(
                    f"Урок {n}",
                    s,
                    e,
                    f"{_minutes_between(s, e)} мин",
                ),
            )
            if i + 1 < len(sorted_nums):
                n_next = sorted_nums[i + 1]
                s_next, _ = self.times[n_next]
                self.bells_table.insert(
                    "",
                    "end",
                    values=(
                        "Перемена",
                        e,
                        s_next,
                        f"{_minutes_between(e, s_next)} мин",
                    ),
                    tags=("break",),
                )

        self.bells_table.pack(fill="x")

        ttk.Label(
            tab,
            text="Время одинаково для всех дней недели.",
            foreground="#888",
        ).pack(anchor="w", pady=(10, 0))

    # ---------- Вкладка «Свободные кабинеты» ----------

    def _build_cabinets_tab(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Свободные кабинеты")

        top = ttk.Frame(tab)
        top.pack(fill="x")

        ttk.Label(top, text="День:").grid(row=0, column=0, padx=(0, 6))
        self.cab_day_var = tk.StringVar()
        self.cab_day_box = ttk.Combobox(
            top,
            textvariable=self.cab_day_var,
            values=self.days,
            state="readonly",
            width=18,
        )
        if self.days:
            self.cab_day_box.set(self.days[0])
        self.cab_day_box.grid(row=0, column=1, padx=(0, 16))

        ttk.Label(top, text="Урок:").grid(row=0, column=2, padx=(0, 6))
        self.cab_lesson_var = tk.StringVar()
        self.cab_lesson_box = ttk.Combobox(
            top,
            textvariable=self.cab_lesson_var,
            values=[str(i) for i in range(1, MAX_LESSON + 1)],
            state="readonly",
            width=10,
        )
        self.cab_lesson_box.set("1")
        self.cab_lesson_box.grid(row=0, column=3, padx=(0, 16))

        ttk.Button(
            top,
            text="Найти свободные",
            command=self.on_find_free,
        ).grid(row=0, column=4)
        ttk.Button(
            top,
            text="Сейчас",
            command=self.on_find_now,
        ).grid(row=0, column=5, padx=6)

        self.cab_output = self._make_output_area(tab)

    def on_find_now(self):
        now = datetime.now()
        self.cab_day_box.set(WEEKDAYS_RU[now.weekday()])
        cur_n, next_n = get_lesson_status()
        n = cur_n or next_n or 1
        self.cab_lesson_box.set(str(n))
        self.on_find_free()

    def on_find_free(self):
        day = self.cab_day_var.get()
        lesson_raw = self.cab_lesson_var.get()
        if not day or not lesson_raw:
            self._set_output(self.cab_output, "Выберите день и урок.")
            return
        lesson = int(lesson_raw)

        busy = get_busy_cabinets(day, lesson)
        free = sorted(set(self.all_cabinets) - busy)

        start, end = self.times.get(lesson, ("--:--", "--:--"))
        lines = [
            "Свободные кабинеты",
            f"{day}, {lesson} урок ({start}–{end})",
            "",
        ]
        if not free:
            lines.append("  Свободных кабинетов нет.")
        else:
            for c in free:
                lines.append(f"  • {c}")
            lines.append("")
            lines.append(f"Всего свободно: {len(free)} из {len(self.all_cabinets)}")

        self._set_output(self.cab_output, "\n".join(lines))

    # ---------- Утилиты интерфейса ----------

    def _make_output_area(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(10, 0))

        text = tk.Text(
            frame,
            wrap="word",
            font=("Consolas", 11),
            relief="solid",
            borderwidth=1,
        )
        text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(frame, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.config(yscrollcommand=scroll.set, state="disabled")

        text.tag_configure("bold", font=("Consolas", 11, "bold"))
        return text

    @staticmethod
    def _set_output(widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")

        for line in text.split("\n"):
            is_bold = "← идёт сейчас" in line
            widget.insert("end", line + "\n", ("bold",) if is_bold else ())

        widget.config(state="disabled")


def main():
    root = tk.Tk()
    SchedLiteApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
