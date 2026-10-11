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
MAX_LESSON = 8


# ==================== ПАЛИТРЫ ====================

LIGHT = {
    "bg": "#f0f0f0",
    "fg": "#000000",
    "button_bg": "#e1e1e1",
    "button_fg": "#000000",
    "button_active": "#d0d0d0",
    "chat_bg": "#ffffff",
    "chat_fg": "#000000",
    "bot_bubble": "#e8f0fe",
    "user_bubble": "#a0dedc",
    "bubble_fg": "#000000",
    "meta_fg": "#7a7a7a",
}

DARK = {
    "bg": "#2b2b2b",
    "fg": "#e0e0e0",
    "button_bg": "#3c3f41",
    "button_fg": "#e0e0e0",
    "button_active": "#4a4a4a",
    "chat_bg": "#1e1e1e",
    "chat_fg": "#e0e0e0",
    "bot_bubble": "#2a3a4a",
    "user_bubble": "#1f5c5c",
    "bubble_fg": "#e0e0e0",
    "meta_fg": "#8a8a8a",
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
            text = SETTINGS_PATH.read_text("utf-8")
            return json.loads(text)
        except Exception:
            return {}
    return {}


def save_settings(data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    SETTINGS_PATH.write_text(text, "utf-8")


# ==================== БАЗА ====================


def db_connect():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Не найден файл базы данных:\n{DB_PATH}\n\n")
    return sqlite3.connect(DB_PATH)


def load_classes():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT class_name FROM classes ORDER BY CAST(grade AS INTEGER), class_name"
        )
        rows = cur.fetchall()

        result = []
        for row in rows:
            class_name = row[0]
            result.append(class_name)
        return result


def load_lesson_times():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT lesson_number, start_time, end_time FROM lesson_times")
        rows = cur.fetchall()

        result = {}
        for row in rows:
            lesson_number = row[0]
            start_time = row[1]
            end_time = row[2]
            result[lesson_number] = (start_time, end_time)
        return result


def load_days():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT day_of_week FROM schedule")
        rows = cur.fetchall()

        found = set()
        for row in rows:
            day = row[0]
            found.add(day)

    result = []
    for day in WEEKDAYS_RU:
        if day in found:
            result.append(day)
    return result


def get_letters_for_grade(grade):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT class_name FROM classes WHERE grade = ? ORDER BY class_name",
            (grade,),
        )
        rows = cur.fetchall()

        letters = []
        for row in rows:
            name = row[0]
            letter = name[len(grade) :]
            if letter and letter not in letters:
                letters.append(letter)
        return letters


def _split_cabinets(raw):
    parts = raw.split("/")
    result = []
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            result.append(cleaned)
    return result


def get_all_cabinets():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT cabinet FROM schedule")
        rows = cur.fetchall()

        result = set()
        for row in rows:
            cabinet = row[0]
            parts = _split_cabinets(cabinet)
            for part in parts:
                result.add(part)
        return sorted(result)


def get_busy_cabinets(day, lesson):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT cabinet FROM schedule "
            "WHERE day_of_week = ? AND lesson_number = ?",
            (day, lesson),
        )
        rows = cur.fetchall()

        result = set()
        for row in rows:
            cabinet = row[0]
            parts = _split_cabinets(cabinet)
            for part in parts:
                result.add(part)
        return result


# ==================== ТЕКСТ ====================


def format_lesson_row(lesson_number, times, lesson, cabinet, mark=""):
    if lesson_number in times:
        start, end = times[lesson_number]
    else:
        start = "--:--"
        end = "--:--"
    return f"  {lesson_number}. {start}–{end}  {lesson}  (каб. {cabinet}){mark}"


def get_lesson_status():
    times = load_lesson_times()
    now = datetime.now().strftime("%H:%M")
    current = None
    next_lesson = None

    sorted_numbers = sorted(times)
    for n in sorted_numbers:
        s = times[n][0]
        e = times[n][1]
        if s <= now <= e:
            current = n
        elif now < s and next_lesson is None:
            next_lesson = n

    return current, next_lesson


def get_current_interval():
    times = load_lesson_times()
    if not times:
        return ("none", None)

    now = datetime.now().strftime("%H:%M")
    sorted_nums = sorted(times)

    first_start = times[sorted_nums[0]][0]
    if now < first_start:
        return ("before", None)

    i = 0
    while i < len(sorted_nums):
        n = sorted_nums[i]
        s = times[n][0]
        e = times[n][1]

        if s <= now <= e:
            return ("lesson", n)

        if i + 1 < len(sorted_nums):
            n_next = sorted_nums[i + 1]
            s_next = times[n_next][0]
            if e < now < s_next:
                return ("break", n)

        i = i + 1

    return ("after", None)


def build_output(class_filter, day_filter, lesson_filter, highlight=False):
    if not class_filter:
        return "Класс не выбран."

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
        rows = cur.fetchall()
        classes = []
        for row in rows:
            classes.append(row[0])

    if not classes:
        conn.close()
        return f"Класс «{class_filter}» не найден."

    times = load_lesson_times()

    if day_filter:
        days = [day_filter]
    else:
        placeholders = "?"
        j = 1
        while j < len(classes):
            placeholders = placeholders + ",?"
            j = j + 1

        query = (
            "SELECT DISTINCT day_of_week FROM schedule "
            "WHERE class_name IN (" + placeholders + ")"
        )
        cur.execute(query, classes)
        rows = cur.fetchall()

        found = set()
        for row in rows:
            found.add(row[0])

        days = []
        for d in WEEKDAYS_RU:
            if d in found:
                days.append(d)

    if not days:
        conn.close()
        return "Расписание для выбранного класса пока не заполнено."

    if highlight:
        status = get_lesson_status()
        current_n = status[0]
        next_n = status[1]
    else:
        current_n = None
        next_n = None

    today_name = WEEKDAYS_RU[datetime.now().weekday()]

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
                query = query + " AND lesson_number = ?"
                params.append(lesson_filter)
            query = query + " ORDER BY lesson_number"

            cur.execute(query, params)
            rows = cur.fetchall()

            if not rows:
                lines.append("    (нет данных)")
            else:
                for row in rows:
                    n = row[0]
                    lesson = row[1]
                    cabinet = row[2]

                    mark = ""
                    if highlight and day == today_name:
                        if n == current_n:
                            mark = "   ← идёт сейчас"
                        elif n == next_n:
                            mark = "   ← следующий"

                    line = format_lesson_row(n, times, lesson, cabinet, mark)
                    lines.append(line)
            lines.append("")
        lines.append("")

    conn.close()
    return "\n".join(lines).rstrip()


def _minutes_between(start, end):
    start_parts = start.split(":")
    h1 = int(start_parts[0])
    m1 = int(start_parts[1])

    end_parts = end.split(":")
    h2 = int(end_parts[0])
    m2 = int(end_parts[1])

    return (h2 * 60 + m2) - (h1 * 60 + m1)


# ==================== ЧАТ НА CANVAS ====================


class ChatView:
    def __init__(self, parent, palette):
        self.palette = palette
        self.messages = []

        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.frame, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self.frame, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.y = 12
        self.font_msg = ("Segoe UI", 11)
        self.font_meta = ("Segoe UI", 9, "bold")

        self._apply_palette()

    def _apply_palette(self):
        self.canvas.configure(bg=self.palette["chat_bg"])

    def set_palette(self, palette):
        self.palette = palette
        self._apply_palette()
        self.redraw()

    def add_message(self, text, side="left", meta=None):
        self.messages.append((text, side, meta))
        self._draw_message(text, side, meta)
        self.canvas.yview_moveto(1.0)

    def redraw(self):
        self.canvas.delete("all")
        self.y = 12

        for message in self.messages:
            text = message[0]
            side = message[1]
            meta = message[2]
            self._draw_message(text, side, meta, scroll=False)

        self.canvas.yview_moveto(1.0)

    def _rounded_rect(self, x1, y1, x2, y2, r, fill):
        points = [
            x1 + r,
            y1,
            x1 + r,
            y1,
            x2 - r,
            y1,
            x2 - r,
            y1,
            x2,
            y1,
            x2,
            y1 + r,
            x2,
            y1 + r,
            x2,
            y2 - r,
            x2,
            y2 - r,
            x2,
            y2,
            x2 - r,
            y2,
            x2 - r,
            y2,
            x1 + r,
            y2,
            x1 + r,
            y2,
            x1,
            y2,
            x1,
            y2 - r,
            x1,
            y2 - r,
            x1,
            y1 + r,
            x1,
            y1 + r,
            x1,
            y1,
            x1,
            y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, fill=fill, outline=fill)

    def _draw_message(self, text, side, meta, scroll=True):
        self.canvas.update_idletasks()
        cw = self.canvas.winfo_width()
        if cw < 50:
            cw = 500

        pad = 12
        radius = 12
        max_bubble = int(cw * 0.78)
        max_text = max_bubble - 2 * pad

        if meta:
            if side == "left":
                meta_x = 16
                meta_anchor = "nw"
            else:
                meta_x = cw - 16
                meta_anchor = "ne"

            self.canvas.create_text(
                meta_x,
                self.y,
                text=meta,
                anchor=meta_anchor,
                fill=self.palette["meta_fg"],
                font=self.font_meta,
            )
            self.y = self.y + 18

        if side == "left":
            text_anchor = "nw"
            text_x = 16 + pad
        else:
            text_anchor = "ne"
            text_x = cw - 16 - pad

        item = self.canvas.create_text(
            text_x,
            self.y + pad,
            text=text,
            anchor=text_anchor,
            width=max_text,
            font=self.font_msg,
            fill=self.palette["bubble_fg"],
            justify="left",
        )

        bbox = self.canvas.bbox(item)
        if not bbox:
            bbox = (text_x, self.y, text_x, self.y + 1)

        x1 = bbox[0]
        y1 = bbox[1]
        x2 = bbox[2]
        y2 = bbox[3]

        rx1 = x1 - pad
        ry1 = y1 - pad
        rx2 = x2 + pad
        ry2 = y2 + pad

        if side == "left":
            color = self.palette["bot_bubble"]
        else:
            color = self.palette["user_bubble"]

        rect = self._rounded_rect(rx1, ry1, rx2, ry2, radius, color)
        self.canvas.tag_lower(rect, item)

        self.y = ry2 + 12
        self.canvas.configure(scrollregion=(0, 0, cw, self.y + 12))

        if scroll:
            self.canvas.yview_moveto(1.0)


# ==================== ПРИЛОЖЕНИЕ ====================


def make_callback(func, arg):

    def callback():
        func(arg)

    return callback


class SchedLiteTgApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SchedLite — помощник расписания")
        self.root.geometry("780x800")
        self.root.minsize(640, 620)

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

        grades_set = set()
        for c in self.classes:
            grade = c[: len(c) - 1]
            grades_set.add(grade)
        self.grades = sorted(grades_set, key=int)

        self.state = "menu"
        self.selected_grade = None
        self.selected_letter = None
        self.selected_day = None
        self.cab_day = None
        self.cab_lesson = None

        self._build_ui()
        self._apply_theme()

        self.root.after(60, self._show_welcome)

    # ---------- Интерфейс ----------

    def _build_ui(self):
        bottom_bar = ttk.Frame(self.root, padding=(8, 4))
        bottom_bar.pack(side="bottom", fill="x")

        self.theme_btn = ttk.Button(
            bottom_bar, text="🌙", width=4, command=self.toggle_theme
        )
        self.theme_btn.pack(side="right")

        self.buttons_frame = ttk.Frame(self.root, padding=(8, 4))
        self.buttons_frame.pack(side="bottom", fill="x")

        chat_frame = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        chat_frame.pack(side="top", fill="both", expand=True)

        if self.theme == "dark":
            p = DARK
        else:
            p = LIGHT
        self.chat = ChatView(chat_frame, p)

    # ---------- Тема ----------

    def toggle_theme(self):
        if self.theme == "dark":
            self.theme = "light"
        else:
            self.theme = "dark"

        self.settings["theme"] = self.theme
        save_settings(self.settings)
        self._apply_theme()

    def _apply_theme(self):
        if self.theme == "dark":
            p = DARK
        else:
            p = LIGHT

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
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", p["button_active"])],
            foreground=[("active", p["button_fg"])],
        )

        style.configure(
            "Vertical.TScrollbar",
            background=p["button_bg"],
            troughcolor=p["bg"],
            borderwidth=0,
            arrowcolor=p["fg"],
        )

        self.chat.set_palette(p)

        if self.theme == "dark":
            self.theme_btn.config(text="☀")
        else:
            self.theme_btn.config(text="🌙")

    # ---------- Сообщения ----------

    def _add_bot_message(self, text):
        self.chat.add_message(text, side="left", meta="SchedLite")

    def _add_user_message(self, text):
        self.chat.add_message(text, side="right", meta="Вы")

    # ---------- Кнопки ----------

    def _clear_buttons(self):
        for w in self.buttons_frame.winfo_children():
            w.destroy()

    def _render_buttons(self, items, cols=3):
        self._clear_buttons()
        i = 0
        for item in items:
            text = item[0]
            cmd = item[1]

            r = i // cols
            c = i % cols

            b = ttk.Button(self.buttons_frame, text=text, command=cmd)
            b.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            i = i + 1

        col = 0
        while col < cols:
            self.buttons_frame.columnconfigure(col, weight=1)
            col = col + 1

    # ---------- Главное меню ----------

    def _show_welcome(self):
        self._add_bot_message(
            "Это электронный помощник.\nДля начала выбери один из пунктов ниже."
        )
        self._show_main_menu()

    def _show_main_menu(self):
        self.state = "menu"
        self.selected_grade = None
        self.selected_letter = None
        self.selected_day = None
        self.cab_day = None
        self.cab_lesson = None

        self._clear_buttons()

        items = [
            ("📅 Расписание", self.on_menu_schedule),
            ("🔔 Звонки", self.on_bells),
            ("🚪 Кабинеты", self.on_cabinets),
            ("⏰ Что сейчас?", self.on_what_now),
        ]

        i = 0
        for item in items:
            text = item[0]
            cmd = item[1]
            r = i // 2
            c = i % 2
            b = ttk.Button(self.buttons_frame, text=text, command=cmd)
            b.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            i = i + 1

        self.buttons_frame.columnconfigure(0, weight=1)
        self.buttons_frame.columnconfigure(1, weight=1)

        my = self.settings.get("my_class")
        if my:
            change_text = f"⚙ Сменить мой класс ({my})"
        else:
            change_text = "⚙ Выбрать мой класс"

        b = ttk.Button(
            self.buttons_frame, text=change_text, command=self.on_change_my_class
        )
        b.grid(row=2, column=0, columnspan=2, padx=3, pady=(8, 3), sticky="ew")

    # ---------- Машина состояний ----------

    def _show_current_step(self):
        if self.state == "menu":
            self._show_main_menu()
        elif self.state == "parallel":
            self._step_parallel()
        elif self.state == "letter":
            self._step_letter()
        elif self.state == "day":
            self._step_day()
        elif self.state == "lesson":
            self._step_lesson()
        elif self.state == "cab_day":
            self._step_cab_day()
        elif self.state == "cab_lesson":
            self._step_cab_lesson()

    def _step_parallel(self):
        self._add_bot_message("Выберите параллель:")

        items = [("🏠 Мой класс", self.on_my_class_from_schedule)]
        for g in self.grades:
            items.append((g, make_callback(self.on_grade, g)))
        items.append(("← В меню", self.on_back))

        self._render_buttons(items, cols=4)

    def _step_letter(self):
        self._add_bot_message(
            f"Параллель {self.selected_grade}. Выберите букву класса:"
        )
        letters = get_letters_for_grade(self.selected_grade)

        items = [("Вся параллель", self.on_all_letters)]
        for l in letters:
            items.append((l, make_callback(self.on_letter, l)))
        items.append(("← Назад", self.on_back))

        self._render_buttons(items, cols=3)

    def _step_day(self):
        if self.selected_letter:
            letter_part = self.selected_letter
        else:
            letter_part = ""
        cls = self.selected_grade + letter_part

        self._add_bot_message(f"{cls}. Выберите день:")

        items = [("Вся неделя", self.on_all_days)]
        for d in self.days:
            items.append((d, make_callback(self.on_day, d)))
        items.append(("← Назад", self.on_back))

        self._render_buttons(items, cols=3)

    def _step_lesson(self):
        if self.selected_letter:
            letter_part = self.selected_letter
        else:
            letter_part = ""
        cls = self.selected_grade + letter_part

        self._add_bot_message(f"{cls}, {self.selected_day}. Выберите урок:")

        items = [("Весь день", self.on_all_lessons)]
        n = 1
        while n <= MAX_LESSON:
            items.append((str(n), make_callback(self.on_lesson, n)))
            n = n + 1
        items.append(("← Назад", self.on_back))

        self._render_buttons(items, cols=3)

    def _step_cab_day(self):
        self._add_bot_message("Свободные кабинеты. Выберите день или нажмите «Сейчас»:")

        items = [("⏰ Сейчас", self.on_cab_now)]
        for d in self.days:
            items.append((d, make_callback(self.on_cab_day, d)))
        items.append(("← В меню", self.on_back))

        self._render_buttons(items, cols=3)

    def _step_cab_lesson(self):
        self._add_bot_message(f"{self.cab_day}. Выберите урок:")

        items = []
        n = 1
        while n <= MAX_LESSON:
            items.append((str(n), make_callback(self.on_cab_lesson, n)))
            n = n + 1
        items.append(("← Назад", self.on_back))

        self._render_buttons(items, cols=4)

    # ---------- Обработчики ----------

    def on_menu_schedule(self):
        self._add_user_message("📅 Расписание")
        self.state = "parallel"
        self._show_current_step()

    def on_grade(self, grade):
        self.selected_grade = grade
        self.selected_letter = None
        self._add_user_message(f"Параллель: {grade}")
        self.state = "letter"
        self._show_current_step()

    def on_all_letters(self):
        self._add_user_message("Вся параллель")
        self.selected_letter = None
        self.selected_day = None
        self._show_schedule_result(None)

    def on_letter(self, letter):
        self.selected_letter = letter
        self._add_user_message(f"Класс: {self.selected_grade}{letter}")
        self.state = "day"
        self._show_current_step()

    def on_all_days(self):
        self._add_user_message("Вся неделя")
        self.selected_day = None
        self._show_schedule_result(None)

    def on_day(self, day):
        self.selected_day = day
        self._add_user_message(f"День: {day}")
        self.state = "lesson"
        self._show_current_step()

    def on_all_lessons(self):
        self._add_user_message("Весь день")
        self._show_schedule_result(None)

    def on_lesson(self, n):
        self._add_user_message(f"Урок {n}")
        self._show_schedule_result(n)

    def _show_schedule_result(self, lesson):
        if self.selected_letter:
            letter_part = self.selected_letter
        else:
            letter_part = ""
        class_filter = self.selected_grade + letter_part

        text = build_output(
            class_filter,
            self.selected_day,
            lesson,
            highlight=True,
        )
        self._add_bot_message(text)
        self._show_main_menu()

    # ---------- Мой класс из подменю Расписание ----------

    def on_my_class_from_schedule(self):
        self._add_user_message("🏠 Мой класс")

        my = self.settings.get("my_class")
        if not my:
            self._ask_my_class()
            my = self.settings.get("my_class")

        if not my:
            self._add_bot_message(
                "Ты пока не выбрал свой класс.\n"
                "Нажми «⚙ Выбрать мой класс» в главном меню."
            )
            self._show_main_menu()
            return

        text = build_output(my, None, None, highlight=True)
        if "нет данных" in text or "не заполнено" in text:
            text = f"{my}:\n  (нет данных)"
        self._add_bot_message(text)
        self._show_main_menu()

    # ---------- Что сейчас? ----------

    def on_what_now(self):
        self._add_user_message("⏰ Что сейчас?")

        now = datetime.now()
        day_name = WEEKDAYS_RU[now.weekday()]
        my = self.settings.get("my_class")

        interval = get_current_interval()
        kind = interval[0]

        if day_name not in self.days:
            self._add_bot_message(f"Сегодня {day_name} — уроков нет.")
            self._show_main_menu()
            return

        if kind == "after":
            self._add_bot_message("⏰ Уроки на сегодня закончились.")
            self._show_main_menu()
            return

        if my:
            self._show_what_now_class(my, day_name)
        else:
            self._show_what_now_bells()

        self._show_main_menu()

    def _show_what_now_class(self, my, day_name):
        text = build_output(my, day_name, None, highlight=True)
        if "нет данных" in text or "не заполнено" in text:
            text = f"{my}\n  {day_name}:\n    (нет уроков или расписание не заполнено)"
        self._add_bot_message(text)

    def _show_what_now_bells(self):
        interval = get_current_interval()
        kind = interval[0]
        num = interval[1]

        if kind == "lesson":
            header = f"⏰ Сейчас идёт {num}-й урок"
        elif kind == "break":
            header = "⏰ Сейчас перемена"
        elif kind == "before":
            header = "⏰ Уроки ещё не начались"
        elif kind == "none":
            header = "⏰ Время уроков не задано"
        else:
            header = "⏰"

        header = header + f"  ({datetime.now().strftime('%H:%M')})"

        lines = [header, "", "🔔 Расписание звонков", ""]
        sorted_nums = sorted(self.times)

        i = 0
        while i < len(sorted_nums):
            n = sorted_nums[i]
            s = self.times[n][0]
            e = self.times[n][1]

            if kind == "lesson" and n == num:
                mark = "   ← СЕЙЧАС"
            else:
                mark = ""
            lines.append(f"  Урок {n}: {s}–{e}  ({_minutes_between(s, e)} мин){mark}")

            if i + 1 < len(sorted_nums):
                n_next = sorted_nums[i + 1]
                s_next = self.times[n_next][0]

                if kind == "break" and n == num:
                    mark = "   ← СЕЙЧАС"
                else:
                    mark = ""
                lines.append(
                    f"  Перемена: {e}–{s_next}  "
                    f"({_minutes_between(e, s_next)} мин){mark}"
                )

            i = i + 1

        if kind == "before":
            lines.append("")
            lines.append(
                "💡 Укажи свой класс в главном меню, чтобы видеть расписание дня."
            )

        self._add_bot_message("\n".join(lines))

    # ---------- Смена моего класса ----------

    def on_change_my_class(self):
        self._add_user_message("⚙ Мой класс")
        self._ask_my_class()
        my = self.settings.get("my_class")
        if my:
            self._add_bot_message(f"Твой класс: {my}")
        self._show_main_menu()

    def _ask_my_class(self):
        win = tk.Toplevel(self.root)
        win.title("Мой класс")
        win.geometry("320x190")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="Выберите свой класс:").pack(pady=(16, 6))

        var = tk.StringVar(value=self.settings.get("my_class", ""))
        box = ttk.Combobox(
            win, textvariable=var, values=self.classes, state="readonly", width=18
        )
        box.pack()

        def ok():
            if var.get():
                self.settings["my_class"] = var.get()
                save_settings(self.settings)
            win.destroy()

        ttk.Button(win, text="Сохранить", command=ok).pack(pady=10)
        self.root.wait_window(win)

    # ---------- Звонки ----------

    def on_bells(self):
        self._add_user_message("🔔 Расписание звонков")

        lines = ["🔔 Расписание звонков", ""]
        sorted_nums = sorted(self.times)

        i = 0
        while i < len(sorted_nums):
            n = sorted_nums[i]
            s = self.times[n][0]
            e = self.times[n][1]
            lines.append(f"  Урок {n}: {s}–{e}  ({_minutes_between(s, e)} мин)")

            if i + 1 < len(sorted_nums):
                n_next = sorted_nums[i + 1]
                s_next = self.times[n_next][0]
                lines.append(
                    f"  Перемена: {e}–{s_next}  ({_minutes_between(e, s_next)} мин)"
                )

            i = i + 1

        self._add_bot_message("\n".join(lines))
        self._show_main_menu()

    # ---------- Свободные кабинеты ----------

    def on_cabinets(self):
        self._add_user_message("🚪 Свободные кабинеты")
        self.cab_day = None
        self.cab_lesson = None
        self.state = "cab_day"
        self._show_current_step()

    def on_cab_now(self):
        now = datetime.now()
        day_name = WEEKDAYS_RU[now.weekday()]

        if day_name not in self.days:
            self._add_user_message("⏰ Сейчас")
            self._add_bot_message(f"Сегодня {day_name} — уроков нет.")
            self._show_main_menu()
            return

        interval = get_current_interval()
        kind = interval[0]
        if kind == "after":
            self._add_user_message("⏰ Сейчас")
            self._add_bot_message("⏰ Уроки на сегодня закончились.")
            self._show_main_menu()
            return

        status = get_lesson_status()
        cur_n = status[0]
        next_n = status[1]

        if cur_n is not None:
            n = cur_n
        else:
            n = next_n
        if n is None:
            n = 1

        self.cab_day = day_name
        self.cab_lesson = n
        self._add_user_message(f"⏰ Сейчас ({day_name}, урок {n})")
        self._show_free_cabinets(day_name, n)
        self._show_main_menu()

    def on_cab_day(self, day):
        self.cab_day = day
        self._add_user_message(f"День: {day}")
        self.state = "cab_lesson"
        self._show_current_step()

    def on_cab_lesson(self, n):
        self.cab_lesson = n
        self._add_user_message(f"Урок {n}")
        self._show_free_cabinets(self.cab_day, n)
        self._show_main_menu()

    def _show_free_cabinets(self, day, n):
        busy = get_busy_cabinets(day, n)

        # Свободные = все минус занятые
        free_set = set()
        for c in self.all_cabinets:
            if c not in busy:
                free_set.add(c)
        free = sorted(free_set)

        if n in self.times:
            start = self.times[n][0]
            end = self.times[n][1]
        else:
            start = "--:--"
            end = "--:--"

        lines = [
            f"🚪 Свободные кабинеты ({day}, {n} урок {start}–{end})",
            "",
        ]

        if not free:
            lines.append("  Свободных кабинетов нет.")
        else:
            for c in free:
                lines.append(f"  • {c}")
            lines.append("")
            lines.append(f"Всего свободно: {len(free)} из {len(self.all_cabinets)}")

        self._add_bot_message("\n".join(lines))

    # ---------- Навигация ----------

    def on_back(self):
        if self.state == "parallel":
            self._add_user_message("← В меню")
            self._show_main_menu()

        elif self.state == "letter":
            self.state = "parallel"
            self.selected_grade = None
            self._show_current_step()

        elif self.state == "day":
            self.state = "letter"
            self.selected_letter = None
            self._show_current_step()

        elif self.state == "lesson":
            self.state = "day"
            self.selected_day = None
            self._show_current_step()

        elif self.state == "cab_day":
            self._add_user_message("← В меню")
            self._show_main_menu()

        elif self.state == "cab_lesson":
            self.state = "cab_day"
            self.cab_lesson = None
            self._show_current_step()


def main():
    root = tk.Tk()
    SchedLiteTgApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
