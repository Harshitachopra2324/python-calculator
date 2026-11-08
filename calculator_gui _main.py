# ==============================================================
# Project     : Calculator with Voice Input (GUI)
# Author      : Harshita
# Language    : Python 3 + Tkinter
# Description : A clean dark-theme calculator. The main window has
#               the basic keys. The "Advance" window has sin, cos,
#               tan, inverse trigonometry, log, ln, root, power,
#               factorial and more. It also has history, keyboard
#               support and voice input.
#
# Code structure:
#   PART 1  Calculation logic (safe evaluator, voice parser)
#   PART 2  Theme and main window
#   PART 3  Key actions
#   PART 4  Voice input
#   PART 5  Keypads and Advance window
# ==============================================================

import ast
import ctypes
import math
import operator
import queue
import re
import threading
import tkinter as tk


# ==============================================================
# PART 1 : CALCULATION LOGIC (no GUI code here)
# ==============================================================

angle_mode = "DEG"          # trigonometry works in degrees or radians


def to_radians(x):
    """Convert an angle to radians when the calculator is in DEG mode."""
    return math.radians(x) if angle_mode == "DEG" else x


def from_radians(x):
    """Convert a result from radians to degrees when in DEG mode."""
    return math.degrees(x) if angle_mode == "DEG" else x


def sin_fn(x):
    return math.sin(to_radians(x))


def cos_fn(x):
    return math.cos(to_radians(x))


def tan_fn(x):
    radians = to_radians(x)
    if abs(math.cos(radians)) < 1e-12:            # tan(90) is not defined
        raise ValueError("tan is not defined for this angle")
    return math.tan(radians)


def asin_fn(x):
    return from_radians(math.asin(x))


def acos_fn(x):
    return from_radians(math.acos(x))


def atan_fn(x):
    return from_radians(math.atan(x))


def factorial_fn(x):
    if x < 0 or x != int(x) or x > 170:
        raise ValueError("factorial needs a whole number from 0 to 170")
    return math.factorial(int(x))


FUNCTIONS = {
    "sin": sin_fn, "cos": cos_fn, "tan": tan_fn,
    "asin": asin_fn, "acos": acos_fn, "atan": atan_fn,
    "sqrt": math.sqrt, "log": math.log10, "ln": math.log,
    "fact": factorial_fn,
}

CONSTANTS = {"pi": math.pi, "e": math.e}

BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def eval_node(node):
    """Solve a parsed expression safely (only allowed things work)."""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        left = eval_node(node.left)
        right = eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("power is too large")
        return BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        return UNARY_OPS[type(node.op)](eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS and len(node.args) == 1
            and not node.keywords):
        return FUNCTIONS[node.func.id](eval_node(node.args[0]))
    raise ValueError("unsupported expression")


def prepare(expression):
    """Turn the text shown on the display into a Python expression."""
    expr = expression
    expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")
    expr = expr.replace("²", "**2").replace("π", "pi").replace("√", "sqrt")
    expr = expr.replace("%", "/100")
    # factorial: 5! -> fact(5)   and   (3+2)! -> fact((3+2))
    expr = re.sub(r"(\d+(?:\.\d+)?|pi|e|\([^()]*\))!", r"fact(\1)", expr)
    expr = re.sub(r"(?<![\d.])0+(?=\d)", "", expr)           # 05 -> 5
    # implicit multiplication: 2(3+4), 2pi, 3sin(30), (1+2)(3+4)
    names = r"\(|pi|e|sin|cos|tan|asin|acos|atan|log|ln|sqrt"
    expr = re.sub(r"(\d|\)|pi|e)(?=" + names + ")", r"\1*", expr)
    expr = re.sub(r"(\)|pi|e)(?=\d)", r"\1*", expr)
    open_brackets = expr.count("(") - expr.count(")")        # auto-close
    if open_brackets > 0:
        expr += ")" * open_brackets
    return expr


def format_result(value):
    """Make the answer neat: 4.0 -> 4 and 0.30000000000000004 -> 0.3"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("result is not a real number")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("result is not valid")
        value = round(value, 10)
        if value.is_integer() and abs(value) < 1e15:
            value = int(value)
    if isinstance(value, int):
        return str(value) if abs(value) < 10 ** 15 else format(value, ".10g")
    return format(value, ".12g")


def evaluate(expression):
    """Solve the text from the display and return the answer as text."""
    tree = ast.parse(prepare(expression), mode="eval")
    return format_result(eval_node(tree.body))


# ----- Voice: turn spoken words into an expression -----

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10",
}

SPOKEN_REPLACEMENTS = [
    (r"square root of|square root|root of|root", " √ "),
    (r"to the power of|to the power|raised to|power", " ^ "),
    (r"multiplied by|multiply by|times|into|\bx\b", " × "),
    (r"divided by|divide by|upon|over|\bby\b", " ÷ "),
    (r"plus|add|and", " + "),
    (r"minus|subtract|negative", " - "),
    (r"squared", " ² "),
    (r"cubed", " ^ 3 "),
    (r"percentage|percent|per cent", " % "),
    (r"open bracket|left bracket|open parenthesis", " ( "),
    (r"close bracket|closed bracket|right bracket|close parenthesis", " ) "),
    (r"point|dot", " . "),
    (r"\bpi\b", " π "),
    (r"inverse sine|arc sine|arcsine|sine inverse", " asin "),
    (r"inverse cosine|arc cosine|arccosine|cosine inverse", " acos "),
    (r"inverse tangent|arc tangent|arctangent|tangent inverse", " atan "),
    (r"cosine|\bcos\b", " cos "),
    (r"sine|\bsin\b", " sin "),
    (r"tangent|\btan\b", " tan "),
    (r"natural log|\bln\b", " ln "),
    (r"logarithm|\blog\b", " log "),
]

FUNCTION_TOKENS = ("asin", "acos", "atan", "sin", "cos", "tan", "log", "ln", "√")


def parse_spoken(text):
    """Example: 'sine of 30 plus 5' -> 'sin(30)+5'. Returns '' if unclear."""
    text = text.lower()
    for word, digit in NUMBER_WORDS.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*(?:percent|per cent|%)\s*of\s*(\d+(?:\.\d+)?)",
                  r"\2 × \1 %", text)                        # 50 percent of 200
    text = re.sub(r"factorial of\s*(\d+)", r"\1 !", text)    # factorial of 5
    text = re.sub(r"(\d+)\s*factorial", r"\1 !", text)       # 5 factorial
    for pattern, symbol in SPOKEN_REPLACEMENTS:
        text = re.sub(pattern, symbol, text)
    text = re.sub(r"\b(?!asin\b|acos\b|atan\b|sin\b|cos\b|tan\b|log\b|ln\b)[a-z]+\b",
                  " ", text)                                 # drop other words
    tokens = re.findall(
        r"asin|acos|atan|sin|cos|tan|log|ln|√|π|\d+(?:\.\d+)?|[+\-×÷^²%()!]|\.", text)

    result = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        next_token = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token in FUNCTION_TOKENS and (
                next_token == "π" or re.fullmatch(r"\d+(?:\.\d+)?", next_token)):
            result.extend([token, "(", next_token, ")"])     # sin 30 -> sin(30)
            i += 2
        else:
            result.append(token)
            i += 1
    return "".join(result)


# ==============================================================
# PART 2 : THEME AND MAIN WINDOW
# ==============================================================
# ===== GUI =====

# All colors and fonts are here. Change them in this one place.
FONT_NAME = "Segoe UI"
THEME = {
    "window_bg": "#000000",
    "display_fg": "yellow",
    "expression_fg": "#8a8a8a",
    "ok": "#39FF14",
    "error": "#ff6b6b",
    "busy": "orange",
    # key style: (text color, key color, hover color)
    "num": ("yellow", "#1c1c1c", "#333333"),
    "op": ("orange", "#262626", "#3a3a3a"),
    "func": ("#00e5ff", "#141c1f", "#22343a"),
    "clear": ("#ff6b6b", "#262626", "#3a3a3a"),
    "equal": ("black", "orange", "#ffb84d"),
}

# Grid rows of the main window (top to bottom)
ROW_TOOLBAR, ROW_EXPRESSION, ROW_DISPLAY, ROW_KEYS = 0, 1, 2, 3   # keys: rows 3 to 7

window = tk.Tk()
window.title("Calculator")
window.geometry("360x520")
window.minsize(340, 480)
window.config(bg=THEME["window_bg"])

# Program state
history = []                     # finished calculations are saved here
voice_queue = queue.Queue()      # the voice thread sends messages here
is_listening = False
result_shown = False             # True right after "=" is pressed
second_mode = False              # True when the 2nd key (inverse trig) is on
advance_window = None            # the Advance window (None when closed)
trig_buttons = {}                # sin, cos, tan keys (text changes with 2nd)
second_button = None
angle_button = None
LISTEN_SECONDS = 5               # how long the microphone listens
ERRORS = ("Error", "Cannot divide by 0")
KEEP_ZERO = (".", "+", "-", "×", "÷", "^", "²", "%", ")", "!")

# Display area: a small line on top and the big display below it
expression_label = tk.Label(window, text="", font=(FONT_NAME, 11), anchor="e",
                            fg=THEME["expression_fg"], bg=THEME["window_bg"], padx=12)
expression_label.grid(row=ROW_EXPRESSION, column=0, columnspan=4, sticky="ew")

display = tk.Label(window, text="0", font=(FONT_NAME, 28), anchor="se",
                   fg=THEME["display_fg"], bg=THEME["window_bg"], padx=12, pady=4)
display.grid(row=ROW_DISPLAY, column=0, columnspan=4, sticky="nsew")


# ==============================================================
# PART 3 : KEY ACTIONS
# ==============================================================

def set_display(text):
    """Show text on the display (font gets smaller for long text)."""
    size = 28 if len(text) <= 11 else 22 if len(text) <= 16 else 17 if len(text) <= 24 else 13
    display.config(text=text, font=(FONT_NAME, size))


def set_top_line(text="", color=None):
    """Show text on the small line above the display."""
    expression_label.config(text=text, fg=color or THEME["expression_fg"])


def press(value):
    """Add the pressed value to the display."""
    global result_shown
    current = display.cget("text")
    if current in ERRORS:
        current = "0"
    if result_shown and value not in KEEP_ZERO:
        current = "0"                         # a new number starts after an answer
    result_shown = False
    if current == "0" and value not in KEEP_ZERO:
        current = ""                          # replace the starting 0
    set_top_line()
    set_display(current + value)


def clear():
    """Reset everything to 0."""
    global result_shown
    result_shown = False
    set_top_line()
    set_display("0")


def backspace():
    """Remove the last character."""
    global result_shown
    result_shown = False
    current = display.cget("text")
    if current in ERRORS:
        set_display("0")
        return
    new_text = current[:-1]
    set_display(new_text if new_text else "0")


def negate():
    """Change the sign (plus/minus) of the number or expression."""
    current = display.cget("text")
    if current == "0" or current in ERRORS:
        return
    if result_shown:                                  # flip the sign of an answer
        set_display(current[1:] if current.startswith("-") else "-" + current)
    else:
        set_display("-(" + current + ")")


def reciprocal():
    """1/x : divide 1 by the number on the display."""
    current = display.cget("text")
    if current == "0":
        set_display("Cannot divide by 0")
        return
    if current in ERRORS:
        return
    set_display("1÷(" + current + ")")
    calculate()


def calculate():
    """Solve the expression on the display and show the answer."""
    global result_shown
    expression = display.cget("text")
    if expression in ERRORS:
        return
    try:
        answer = evaluate(expression)
        history.append(expression + " = " + answer)
        set_top_line(expression + " =")
        set_display(answer)
        result_shown = True
    except ZeroDivisionError:
        set_display("Cannot divide by 0")
    except Exception:
        set_display("Error")


def toggle_angle():
    """Switch between DEG and RAD for sin, cos and tan."""
    global angle_mode
    angle_mode = "RAD" if angle_mode == "DEG" else "DEG"
    if angle_button:
        angle_button.config(text=angle_mode)


def toggle_second():
    """2nd key: sin, cos, tan become sin⁻¹, cos⁻¹, tan⁻¹."""
    global second_mode
    second_mode = not second_mode
    show_trig_names()


def show_trig_names():
    """Update the text of the 2nd, sin, cos and tan keys."""
    for name, button in trig_buttons.items():
        button.config(text=name + "⁻¹" if second_mode else name)
    if second_button:
        second_button.config(text="2nd ✔" if second_mode else "2nd")


def dark_title_bar(target):
    """Make the Windows title bar black (Windows 10/11 only)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(target.winfo_id())
        dwm = ctypes.windll.dwmapi
        size = ctypes.sizeof(ctypes.c_int)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), size)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(0x000000)), size)
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(ctypes.c_int(0xFFFFFF)), size)
    except Exception:
        pass                                # other systems: nothing happens


def show_history():
    """Open a window with all past calculations."""
    win = tk.Toplevel(window)
    win.title("History")
    win.geometry("320x380")
    win.config(bg=THEME["window_bg"])
    win.after(150, lambda: dark_title_bar(win))

    box = tk.Listbox(win, font=(FONT_NAME, 12), fg=THEME["display_fg"], bg="#1c1c1c",
                     selectbackground="#444444", bd=0, highlightthickness=0)
    box.pack(fill="both", expand=True, padx=8, pady=8)
    for item in reversed(history):                    # newest on top
        box.insert(tk.END, item)

    def use_result(event):
        """Double-click an item to put its answer on the display."""
        selected = box.curselection()
        if selected:
            set_display(box.get(selected[0]).split(" = ")[-1])
            win.destroy()

    def clear_history():
        history.clear()
        box.delete(0, tk.END)

    box.bind("<Double-Button-1>", use_result)
    tk.Button(win, text="Clear history", font=(FONT_NAME, 11), fg="white",
              bg="#cc3333", bd=0, command=clear_history
              ).pack(fill="x", padx=8, pady=(0, 8))


COMMANDS = {
    "clear": clear, "backspace": backspace, "negate": negate,
    "reciprocal": reciprocal, "equal": calculate,
    "second": toggle_second, "angle": toggle_angle,
}


def on_key(action):
    """One place that decides what every calculator key does."""
    if action.startswith("trig:"):
        name = action[5:]
        press(("a" + name if second_mode else name) + "(")
    elif action.startswith("cmd:"):
        COMMANDS[action[4:]]()
    else:
        press(action)


def key_press(event):
    """Let the user type numbers and operators from the keyboard."""
    key = event.char
    if key == "*":
        press("×")
    elif key == "/":
        press("÷")
    elif key == "p":
        press("π")
    elif key and key in "0123456789.+-()%^!":
        press(key)
    elif event.keysym == "Return":
        calculate()
    elif event.keysym == "BackSpace":
        backspace()
    elif event.keysym == "Escape" or key == "c":
        clear()


# ==============================================================
# PART 4 : VOICE INPUT
# ==============================================================

def listen_worker():
    """Runs in a separate thread so the window does not freeze."""
    try:
        import speech_recognition as sr
        import sounddevice as sd
    except ImportError:
        voice_queue.put(("error", "Install: py -m pip install SpeechRecognition sounddevice"))
        return
    try:
        rate = 16000
        voice_queue.put(("status", "Listening... speak now"))
        with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16") as stream:
            data, _ = stream.read(rate * LISTEN_SECONDS)
        voice_queue.put(("status", "Understanding..."))
        audio = sr.AudioData(bytes(data), rate, 2)
        heard = sr.Recognizer().recognize_google(audio, language="en-IN")
        voice_queue.put(("heard", heard))
    except sr.UnknownValueError:
        voice_queue.put(("error", "Could not understand, please try again"))
    except sr.RequestError:
        voice_queue.put(("error", "Voice needs an internet connection"))
    except Exception as problem:
        voice_queue.put(("error", "Microphone problem: " + str(problem)[:50]))


def start_listening():
    """Called when the mic button is pressed."""
    global is_listening
    if is_listening:
        return
    is_listening = True
    mic_button.config(text="🎤 Listening...")
    threading.Thread(target=listen_worker, daemon=True).start()


def check_voice_queue():
    """Every 0.1 second: see if the voice thread has sent something."""
    global is_listening
    while not voice_queue.empty():
        kind, message = voice_queue.get_nowait()
        if kind == "status":
            set_top_line(message, THEME["busy"])
            continue
        is_listening = False
        mic_button.config(text="🎤 Speak")
        if kind == "error":
            set_top_line(message, THEME["error"])
        elif kind == "heard":
            expression = parse_spoken(message)
            if expression:
                set_display(expression)
                calculate()
            else:
                set_top_line("Heard: " + message + " (no numbers found)", THEME["error"])
    window.after(100, check_voice_queue)


# ==============================================================
# PART 5 : KEYPADS AND ADVANCE WINDOW
# ==============================================================

# Each key: (text on key, action, style)
MAIN_KEYS = [
    [("C", "cmd:clear", "clear"), ("⌫", "cmd:backspace", "op"),
     ("%", "%", "op"), ("÷", "÷", "op")],
    [("7", "7", "num"), ("8", "8", "num"), ("9", "9", "num"), ("×", "×", "op")],
    [("4", "4", "num"), ("5", "5", "num"), ("6", "6", "num"), ("−", "-", "op")],
    [("1", "1", "num"), ("2", "2", "num"), ("3", "3", "num"), ("+", "+", "op")],
    [("±", "cmd:negate", "op"), ("0", "0", "num"),
     (".", ".", "num"), ("=", "cmd:equal", "equal")],
]

ADVANCE_KEYS = [
    [("2nd", "cmd:second", "func"), ("sin", "trig:sin", "func"),
     ("cos", "trig:cos", "func"), ("tan", "trig:tan", "func")],
    [("π", "π", "func"), ("e", "e", "func"),
     ("log", "log(", "func"), ("ln", "ln(", "func")],
    [("x²", "²", "func"), ("xʸ", "^", "func"),
     ("√", "√(", "func"), ("n!", "!", "func")],
    [("(", "(", "func"), (")", ")", "func"),
     ("1/x", "cmd:reciprocal", "func"), ("DEG", "cmd:angle", "func")],
]


def add_hover(button, normal_color, hover_color):
    """Key color changes slightly when the mouse is on it."""
    button.bind("<Enter>", lambda event: button.config(bg=hover_color))
    button.bind("<Leave>", lambda event: button.config(bg=normal_color))


def build_keys(parent, rows, first_row):
    """Create all keys of a keypad from a table."""
    global second_button, angle_button
    for row_number, row in enumerate(rows, start=first_row):
        for column, (label, action, style) in enumerate(row):
            text_color, key_color, hover_color = THEME[style]
            button = tk.Button(parent, text=label, font=(FONT_NAME, 13),
                               fg=text_color, bg=key_color,
                               activebackground=hover_color, activeforeground=text_color,
                               bd=0, relief="flat", highlightthickness=0, takefocus=0,
                               command=lambda a=action: on_key(a))
            button.grid(row=row_number, column=column, sticky="nsew", padx=2, pady=2)
            add_hover(button, key_color, hover_color)
            if action.startswith("trig:"):
                trig_buttons[action[5:]] = button
            elif action == "cmd:second":
                second_button = button
            elif action == "cmd:angle":
                angle_button = button
                button.config(text=angle_mode)


def close_advance():
    """Called when the Advance window is closed."""
    global advance_window, second_button, angle_button
    trig_buttons.clear()
    second_button = None
    angle_button = None
    if advance_window:
        advance_window.destroy()
    advance_window = None


def open_advance():
    """Open the Advance window (or bring it to the front if already open)."""
    global advance_window
    if advance_window is not None and advance_window.winfo_exists():
        advance_window.lift()
        return

    win = tk.Toplevel(window)
    win.title("Advance")
    win.config(bg=THEME["window_bg"])
    win.minsize(300, 220)

    # place it next to the calculator (on the left if there is no space on the right)
    width, height = 340, 240
    x = window.winfo_rootx() + window.winfo_width() + 10
    if x + width > window.winfo_screenwidth():
        x = max(window.winfo_rootx() - width - 10, 0)
    win.geometry(f"{width}x{height}+{x}+{window.winfo_rooty()}")

    for column in range(4):
        win.columnconfigure(column, weight=1, uniform="keys")
    for row in range(len(ADVANCE_KEYS)):
        win.rowconfigure(row, weight=1, minsize=48)

    advance_window = win
    build_keys(win, ADVANCE_KEYS, 0)
    show_trig_names()                       # keep 2nd mode if it was on
    win.bind("<Key>", key_press)            # keyboard works here too
    win.protocol("WM_DELETE_WINDOW", close_advance)
    win.after(150, lambda: dark_title_bar(win))


# Toolbar (title on the left, buttons on the right)
toolbar = tk.Frame(window, bg=THEME["window_bg"])
toolbar.grid(row=ROW_TOOLBAR, column=0, columnspan=4, sticky="ew", padx=6, pady=(6, 0))
tk.Label(toolbar, text="Calculator", font=(FONT_NAME, 11, "bold"),
         fg=THEME["display_fg"], bg=THEME["window_bg"]).pack(side="left", padx=4)


def toolbar_button(text, color, command):
    button = tk.Button(toolbar, text=text, font=(FONT_NAME, 10), fg=color, bg="#1c1c1c",
                       activebackground="#333333", activeforeground=color, bd=0,
                       relief="flat", padx=10, pady=3, takefocus=0, command=command)
    button.pack(side="right", padx=(4, 0))
    add_hover(button, "#1c1c1c", "#333333")
    return button


history_button = toolbar_button("History", "orange", show_history)
advance_button = toolbar_button("Advance", "#00e5ff", open_advance)
mic_button = toolbar_button("🎤 Speak", THEME["ok"], start_listening)

build_keys(window, MAIN_KEYS, ROW_KEYS)

# Layout: the keys stretch evenly when the window is resized
for column in range(4):
    window.columnconfigure(column, weight=1, uniform="keys")
window.rowconfigure(ROW_EXPRESSION, weight=0, minsize=22)
window.rowconfigure(ROW_DISPLAY, weight=0, minsize=80)
for row in range(ROW_KEYS, ROW_KEYS + len(MAIN_KEYS)):
    window.rowconfigure(row, weight=1, minsize=50)
window.rowconfigure(ROW_KEYS + len(MAIN_KEYS), weight=0, minsize=6)   # small bottom space

window.bind("<Key>", key_press)
window.after(150, lambda: dark_title_bar(window))
check_voice_queue()
window.mainloop()
