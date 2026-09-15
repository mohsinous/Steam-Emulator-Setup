import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import subprocess
import sys
from pathlib import Path
import urllib.request
import urllib.parse
import re
import webbrowser
from io import BytesIO

from PIL import Image, ImageTk


# ============================================================
# COLORS
# ============================================================

BG = "#f4f8fc"
WHITE = "#ffffff"
BLUE = "#1683e8"
BLUE_DARK = "#0d63bd"
TEXT = "#10245a"
TEXT_LIGHT = "#31578e"
BORDER = "#b9d8f5"
LIGHT_BLUE = "#eef7ff"
DARK_BLUE = "#132a5e"


# ============================================================
# PRICE STRIPPING
# ============================================================

# Steam's autocomplete returns the price appended directly to the
# game name, e.g. "Onimusha: Way of the Sword$69.99". This regex
# removes any trailing price token (currency symbol / Free / Free
# To Play / etc.) so only the clean game name remains.
_PRICE_SUFFIX_RE = re.compile(
    r"\s*"
    r"(?:"
    r"[$€£¥₩₹]\s?\d[\d.,]*"          # $69.99  €19,99  £9.99
    r"|"
    r"\d[\d.,]*\s?[$€£¥₩₹]"          # 69,99€  19.99$
    r"|"
    r"\d[\d.,]*\s?(?:USD|EUR|GBP|RUB|BRL|JPY|CNY|KRW|INR)"  # 69.99 USD
    r"|"
    r"Free To Play"
    r"|"
    r"Free"
    r")"
    r"\s*$",
    re.IGNORECASE
)


def strip_price(name):
    """Remove a trailing price token from a Steam autocomplete name."""
    if not name:
        return name

    # Strip repeatedly in case Steam returns something like
    # "Game$9.99 Free" or similar.
    cleaned = name
    for _ in range(3):
        new_cleaned = _PRICE_SUFFIX_RE.sub("", cleaned).strip()
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned

    return cleaned


# ============================================================
# APPLICATION
# ============================================================

class SteamAppIDFinder:

    def __init__(self, root):

        self.root = root

        self.root.title("Steam Emulator Setup")

        # Fixed window size.
        win_w = 820
        win_h = 940

        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(720, 820)

        self.root.configure(bg=BG)

        # Use the custom application icon for the window/title bar.
        # PyInstaller bundles app_icon.ico into its temporary resource directory.
        try:
            self.root.iconbitmap(str(self.get_resource_path("app_icon.ico")))
        except Exception:
            pass

        # Place the window at the top-center of the primary screen
        # (no vertical offset, so the title bar touches y = 0).
        self.root.update_idletasks()

        screen_w = self.root.winfo_screenwidth()

        x = (screen_w - win_w) // 2
        y = 0

        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        self.current_appid = None
        self.current_game = None

        self.banner_image = None
        self.banner_photo = None

        self.steam_icon = None

        # Single fixed column width shared by every widget.
        self.body_width = 720

        # ====================================================
        # TTK STYLE
        # ====================================================

        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Steam.Horizontal.TProgressbar",
            troughcolor="#dcecfb",
            background=BLUE,
            bordercolor="#dcecfb",
            lightcolor=BLUE,
            darkcolor=BLUE
        )

        # ====================================================
        # CONTENT
        # ====================================================

        self.content = tk.Frame(
            root,
            bg=BG
        )

        self.content.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=10
        )

        # ====================================================
        # HEADER
        # ====================================================

        header = tk.Frame(
            self.content,
            bg=BG
        )

        header.pack(
            fill="x",
            pady=(0, 6)
        )

        title_row = tk.Frame(
            header,
            bg=BG
        )

        title_row.pack()

        self.load_steam_icon()

        if self.steam_icon:

            self.icon_label = tk.Label(
                title_row,
                image=self.steam_icon,
                bg=BG
            )

            self.icon_label.pack(
                side="left",
                padx=(0, 12)
            )

        title = tk.Label(
            title_row,
            text="Steam Emulator Setup",
            font=("Segoe UI", 20, "bold"),
            fg=TEXT,
            bg=BG
        )

        title.pack(
            side="left"
        )

        subtitle = tk.Label(
            header,
            text="Search for a Steam game and select the game you want",
            font=("Segoe UI", 10),
            fg=TEXT_LIGHT,
            bg=BG
        )

        subtitle.pack(
            pady=(2, 0)
        )

        # ====================================================
        # BODY WRAPPER
        # ====================================================

        body_wrap = tk.Frame(
            self.content,
            bg=BG
        )

        body_wrap.pack(
            fill="both",
            expand=True
        )

        self.body = tk.Frame(
            body_wrap,
            bg=BG,
            width=self.body_width,
            height=2000
        )

        self.body.pack(
            side="top",
            anchor="n"
        )

        # Lock width and height so children can never resize it.
        self.body.pack_propagate(False)

        # ====================================================
        # SEARCH (full body width; icon button inside the field)
        # ====================================================

        search_row = tk.Frame(
            self.body,
            bg=BG
        )

        search_row.pack(
            fill="x",
            pady=(0, 6)
        )

        entry_frame = tk.Frame(
            search_row,
            bg=WHITE,
            highlightbackground="#74b8f3",
            highlightcolor=BLUE,
            highlightthickness=1
        )

        entry_frame.pack(
            fill="x"
        )

        self.search_entry = tk.Entry(
            entry_frame,
            font=("Segoe UI", 11),
            bg=WHITE,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0
        )

        self.search_entry.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(14, 4),
            pady=7
        )

        self.search_button = tk.Button(
            entry_frame,
            text="🔍",
            font=("Segoe UI", 11, "bold"),
            fg=WHITE,
            bg=BLUE,
            activeforeground=WHITE,
            activebackground=BLUE_DARK,
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.search_games
        )

        self.search_button.pack(
            side="right",
            padx=(0, 4),
            pady=4
        )

        self.search_entry.bind(
            "<Return>",
            lambda event: self.search_games()
        )

        # ====================================================
        # SEARCH RESULTS
        # ====================================================

        results_title = tk.Label(
            self.body,
            text="Search Results",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT,
            bg=BG,
            anchor="w"
        )

        results_title.pack(
            fill="x",
            pady=(0, 3)
        )

        results_frame = tk.Frame(
            self.body,
            bg=WHITE,
            highlightbackground="#72b8f2",
            highlightthickness=1
        )

        results_frame.pack(
            fill="x"
        )

        self.search_results = tk.Listbox(
            results_frame,
            font=("Segoe UI", 10),
            height=4,
            bg=WHITE,
            fg=TEXT,
            selectbackground=BLUE,
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0
        )

        scrollbar_results = tk.Scrollbar(
            results_frame,
            orient="vertical",
            command=self.search_results.yview,
            bg="#dceafa",
            activebackground="#a9cbea",
            relief="flat",
            bd=0
        )

        self.search_results.configure(
            yscrollcommand=scrollbar_results.set
        )

        self.search_results.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(3, 0),
            pady=3
        )

        scrollbar_results.pack(
            side="right",
            fill="y"
        )

        self.search_results.bind(
            "<Double-Button-1>",
            lambda event: self.select_game()
        )

        # ====================================================
        # BANNER PLACEHOLDER
        # ====================================================

        self.banner_frame = None
        self.banner_label = None

        # ====================================================
        # ACTIVITY LOG
        # ====================================================

        self.log_title = tk.Label(
            self.body,
            text="Activity Log",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT,
            bg=BG,
            anchor="w"
        )
        self.log_title.pack(
            fill="x",
            pady=(0, 3)
        )

        log_frame = tk.Frame(
            self.body,
            bg=WHITE,
            highlightbackground=BORDER,
            highlightthickness=1
        )
        log_frame.pack(
            fill="x",
            pady=(0, 8)
        )

        log_scrollbar = tk.Scrollbar(
            log_frame,
            orient="vertical",
            relief="flat",
            bd=0
        )

        self.log_text = tk.Text(
            log_frame,
            height=4,
            font=("Consolas", 8),
            bg="#f8fbff",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            wrap="word",
            state="disabled",
            yscrollcommand=log_scrollbar.set
        )

        log_scrollbar.config(command=self.log_text.yview)
        self.log_text.pack(
            side="left",
            fill="both",
            expand=True,
            padx=8,
            pady=6
        )
        log_scrollbar.pack(
            side="right",
            fill="y"
        )

        self.log("Application ready.")

        # ====================================================
        # WORKFLOW STATE
        # ====================================================

        self.selected_folder = None
        self.steam_api64_paths = []
        self.workflow_running = False
        self.workflow_step = None

        # ====================================================
        # INFORMATION CARD
        # ====================================================

        self.info_card = tk.Frame(
            self.body,
            bg=LIGHT_BLUE,
            highlightbackground=BORDER,
            highlightthickness=1
        )

        self.info_card.pack(
            fill="x",
            pady=(0, 6)
        )

        info_inner = tk.Frame(
            self.info_card,
            bg=LIGHT_BLUE
        )

        info_inner.pack(
            fill="x",
            padx=18,
            pady=7
        )

        # Game row
        game_row = tk.Frame(
            info_inner,
            bg=LIGHT_BLUE
        )

        game_row.pack(
            fill="x",
            pady=(0, 3)
        )

        tk.Label(
            game_row,
            text="Game:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=LIGHT_BLUE,
            width=8,
            anchor="w"
        ).pack(
            side="left"
        )

        self.game_name_label = tk.Label(
            game_row,
            text="-",
            font=("Segoe UI", 10),
            fg=TEXT,
            bg=LIGHT_BLUE,
            anchor="w"
        )

        self.game_name_label.pack(
            side="left"
        )

        # AppID row
        appid_row = tk.Frame(
            info_inner,
            bg=LIGHT_BLUE
        )

        appid_row.pack(
            fill="x"
        )

        tk.Label(
            appid_row,
            text="AppID:",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=LIGHT_BLUE,
            width=8,
            anchor="w"
        ).pack(
            side="left"
        )

        self.appid_label = tk.Label(
            appid_row,
            text="-",
            font=("Segoe UI", 10),
            fg=TEXT,
            bg=LIGHT_BLUE,
            anchor="w"
        )

        self.appid_label.pack(
            side="left"
        )

        # ====================================================
        # ACTION BUTTONS
        # ====================================================

        action_row = tk.Frame(
            self.body,
            bg=BG
        )

        action_row.pack(
            fill="x",
            pady=(0, 6)
        )

        self.copy_button = tk.Button(
            action_row,
            text="▣  Copy AppID",
            font=("Segoe UI", 10, "bold"),
            fg=BLUE_DARK,
            bg=WHITE,
            activebackground=LIGHT_BLUE,
            activeforeground=BLUE_DARK,
            relief="solid",
            bd=1,
            highlightbackground="#70b8f2",
            cursor="hand2",
            pady=6,
            command=self.copy_appid
        )

        self.copy_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8)
        )

        self.steamdb_button = tk.Button(
            action_row,
            text="↗  Open SteamDB",
            font=("Segoe UI", 10, "bold"),
            fg=BLUE_DARK,
            bg=WHITE,
            activebackground=LIGHT_BLUE,
            activeforeground=BLUE_DARK,
            relief="solid",
            bd=1,
            highlightbackground="#70b8f2",
            cursor="hand2",
            pady=6,
            command=self.open_steamdb
        )

        self.steamdb_button.pack(
            side="right",
            fill="x",
            expand=True,
            padx=(8, 0)
        )

        # ====================================================
        # SEPARATOR
        # ====================================================

        separator = tk.Frame(
            self.body,
            bg=BORDER,
            height=1
        )

        separator.pack(
            fill="x",
            pady=(0, 5)
        )

        # ====================================================
        # PROGRESS
        # ====================================================

        self.progress_bar = ttk.Progressbar(
            self.body,
            mode="indeterminate",
            style="Steam.Horizontal.TProgressbar"
        )

        # ====================================================
        # STATUS
        # ====================================================

        self.status_label = tk.Label(
            self.body,
            text="Ready",
            font=("Segoe UI", 10),
            fg=TEXT_LIGHT,
            bg=BG
        )

        self.status_label.pack(
            pady=(0, 2)
        )

        # ====================================================
        # INITIAL STATE
        # ====================================================

        self.copy_button.config(
            state="disabled"
        )

        self.steamdb_button.config(
            state="disabled"
        )

    # ========================================================
    # COMPLETE LOG
    # ========================================================

    def log(self, message):
        """Append a timestamped message to the complete workflow log."""
        from datetime import datetime

        def append_log():
            if not hasattr(self, "log_text"):
                return
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state="disabled")

        if threading.current_thread() is threading.main_thread():
            append_log()
        else:
            self.root.after(0, append_log)

    def log_command_output(self, label, stdout, stderr):
        """Write command output to the log without losing blank/empty output."""
        self.log(f"{label} stdout:")
        if stdout and stdout.strip():
            for line in stdout.rstrip().splitlines():
                self.log("  " + line)
        else:
            self.log("  <no stdout>")

        if stderr and stderr.strip():
            self.log(f"{label} stderr:")
            for line in stderr.rstrip().splitlines():
                self.log("  " + line)

    # ========================================================
    # APPLICATION / HEADER ICON
    # ========================================================

    def get_resource_path(self, name):
        """Return a bundled resource or a resource next to the Python file."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS) / name
        return Path(__file__).resolve().parent / name

    def load_steam_icon(self):
        """Load the custom icon for the header instead of Steam's favicon."""
        try:
            icon_path = self.get_resource_path("app_icon.ico")
            image = Image.open(icon_path).convert("RGBA")
            image = image.resize(
                (64, 64),
                Image.Resampling.LANCZOS
            )
            self.steam_icon = ImageTk.PhotoImage(image)

            # Keep the window icon identical to the header icon.
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                self.root.iconphoto(True, self.steam_icon)

        except Exception as error:
            self.steam_icon = None
            # Avoid calling self.log here if logging widgets are not initialized yet.
            print(f"Could not load custom application icon: {error}")

    # ========================================================
    # START LOADING
    # ========================================================

    def start_loading(self, text):

        self.status_label.config(
            text=text
        )

        self.progress_bar.pack(
            fill="x",
            pady=(0, 4)
        )

        self.progress_bar.start(10)

    # ========================================================
    # STOP LOADING
    # ========================================================

    def stop_loading(self):

        self.progress_bar.stop()

        self.progress_bar.pack_forget()

    # ========================================================
    # SEARCH
    # ========================================================

    def search_games(self):

        query = self.search_entry.get().strip()

        if not query:

            messagebox.showwarning(
                "Search",
                "Please enter a game name."
            )

            return

        self.search_button.config(
            state="disabled"
        )

        self.search_results.delete(
            0,
            tk.END
        )

        self.start_loading(
            "Searching Steam..."
        )

        threading.Thread(
            target=self.perform_search,
            args=(query,),
            daemon=True
        ).start()

    # ========================================================
    # PERFORM SEARCH
    # ========================================================

    def perform_search(self, query):

        try:

            encoded_query = urllib.parse.quote(
                query
            )

            url = (
                "https://store.steampowered.com/search/suggest/"
                "?term="
                + encoded_query
                + "&f=games"
                + "&cc=US"
                + "&realm=1"
                + "&l=english"
            )

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120 Safari/537.36"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=15
            ) as response:

                html = response.read().decode(
                    "utf-8",
                    errors="ignore"
                )

            patterns = [

                r'data-ds-appid="([^"]+)"'
                r'[^>]*data-ds-match-name="([^"]+)"',

                r'data-ds-appid="([^"]+)"'
                r'.*?data-ds-match-name="([^"]+)"',

                r'data-ds-appid="([^"]+)"'
                r'[^>]*>(.*?)</a>'
            ]

            matches = []

            for pattern in patterns:

                matches = re.findall(
                    pattern,
                    html,
                    re.IGNORECASE | re.DOTALL
                )

                if matches:
                    break

            results = []

            for item in matches:

                if len(item) < 2:
                    continue

                appid = str(
                    item[0]
                ).split(",")[0].strip()

                name = re.sub(
                    r"<.*?>",
                    "",
                    str(item[1])
                ).strip()

                name = (
                    name
                    .replace("&amp;", "&")
                    .replace("&#39;", "'")
                    .replace("&quot;", '"')
                )

                # Strip any trailing price token from the name so
                # the search result shows only the game title.
                name = strip_price(name)

                if appid.isdigit() and name:

                    result = (
                        name,
                        appid
                    )

                    if result not in results:
                        results.append(result)

            self.root.after(
                0,
                self.display_results,
                results
            )

        except Exception as error:

            self.root.after(
                0,
                self.search_failed,
                str(error)
            )

    # ========================================================
    # DISPLAY RESULTS
    # ========================================================

    def display_results(self, results):

        self.stop_loading()

        self.search_button.config(
            state="normal"
        )

        self.search_results.delete(
            0,
            tk.END
        )

        if not results:

            self.status_label.config(
                text="No games found."
            )

            messagebox.showinfo(
                "Search Results",
                "No Steam games were found."
            )

            return

        for name, appid in results:

            self.search_results.insert(
                tk.END,
                f"{name}   [AppID: {appid}]"
            )

        self.status_label.config(
            text=f"{len(results)} game(s) found. Double-click a result to select."
        )

    # ========================================================
    # SEARCH FAILED
    # ========================================================

    def search_failed(self, error):

        self.stop_loading()

        self.search_button.config(
            state="normal"
        )

        self.status_label.config(
            text="Search failed."
        )

        messagebox.showerror(
            "Search Error",
            "Unable to search Steam.\n\n"
            + error
        )

    # ========================================================
    # WORKFLOW PATHS
    # ========================================================

    def get_application_directory(self):
        """Return the directory containing the running EXE, or main.py when running from source."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def get_step_folder(self, name):
        return self.get_application_directory() / name

    def get_workflow_paths(self, appid):
        app_dir = self.get_application_directory()
        step1 = app_dir / "01_STEP"
        step2 = app_dir / "02_STEP"
        step3 = app_dir / "03_STEP"
        output_appid = step1 / "output" / str(appid)
        settings = output_appid / "steam_settings"
        return step1, step2, step3, output_appid, settings

    def validate_step_folders(self):
        missing = []
        for name in ("01_STEP", "02_STEP", "03_STEP"):
            folder = self.get_step_folder(name)
            if not folder.is_dir():
                missing.append(str(folder))

        if missing:
            messagebox.showerror(
                "Required Folders Missing",
                "Please make sure these three folders exist next to Steam AppID Finder.exe:\n\n"
                + "\n".join(missing)
            )
            return False

        return True

    # ========================================================
    # STEP 1 - GENERATE EMU CONFIG
    # ========================================================

    def start_workflow(self):
        if not self.current_appid:
            return

        if not self.validate_step_folders():
            return

        self.workflow_running = True
        self.workflow_step = 1
        self.log("=" * 70)
        self.log(f"Workflow started for AppID {self.current_appid}.")
        self.log("Step 1/5: preparing generate_emu_config.exe")

        self.start_loading(
            f"Step 1/5 - Generating configuration for AppID {self.current_appid}..."
        )

        threading.Thread(
            target=self.run_generate_emu_config,
            args=(self.current_appid,),
            daemon=True
        ).start()

    def run_generate_emu_config(self, appid):
        try:
            step1, _, _, output_appid, _ = self.get_workflow_paths(appid)
            generator = step1 / "generate_emu_config.exe"

            if not generator.is_file():
                raise FileNotFoundError(
                    f"generate_emu_config.exe was not found in:\n{generator}"
                )

            self.log(f"Running: generate_emu_config.exe {appid}")
            self.log(f"Working directory: {step1}")

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [str(generator), str(appid)],
                cwd=str(step1),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            self.log(f"generate_emu_config.exe exited with code {result.returncode}.")
            self.log_command_output("generate_emu_config.exe", result.stdout, result.stderr)

            if result.returncode != 0:
                details = result.stderr.strip() or result.stdout.strip() or "The generator returned an error."
                raise RuntimeError(details)

            if not output_appid.is_dir():
                raise FileNotFoundError(
                    "The generator finished, but the expected output folder was not created:\n"
                    + str(output_appid)
                )

            info_folder = output_appid / "info"
            if info_folder.exists():
                import shutil
                shutil.rmtree(info_folder)
                self.log(f"Deleted info folder: {info_folder}")
            else:
                self.log(f"info folder was not present: {info_folder}")

            self.log(f"Step 1 complete. Output folder: {output_appid}")
            self.root.after(0, self.step1_finished, output_appid)

        except subprocess.TimeoutExpired:
            self.root.after(0, self.workflow_failed, "Step 1 timed out while running generate_emu_config.exe.")
        except Exception as error:
            self.root.after(0, self.workflow_failed, str(error))

    def step1_finished(self, output_appid):
        self.workflow_step = 2
        self.log("Step 2/5: opening the game-folder picker automatically.")
        self.status_label.config(
            text="Step 2/5 - Configuration generated and info folder deleted."
        )
        self.stop_loading()

        self.root.after(250, self.choose_folder)

    # ========================================================
    # STEP 3 - CHOOSE GAME FOLDER / FIND DLL
    # ========================================================

    def choose_folder(self):
        if not self.workflow_running or self.workflow_step < 2:
            return

        folder = filedialog.askdirectory(
            title="Select Game Folder"
        )

        if not folder:
            self.status_label.config(
                text="Step 2 complete. Please select a game folder to continue."
            )
            return

        self.selected_folder = Path(folder)
        self.log(f"Game folder selected: {self.selected_folder}")
        self.log("Step 3/5: searching recursively for steam_api64.dll")
        self.steam_api64_paths = []
        self.workflow_step = 3

        self.start_loading("Step 3/5 - Searching for steam_api64.dll...")

        threading.Thread(
            target=self.find_steam_api64,
            args=(self.selected_folder,),
            daemon=True
        ).start()

    def find_steam_api64(self, folder):
        found = []

        try:
            import os

            for root, dirs, files in os.walk(
                folder,
                topdown=True,
                onerror=lambda error: None
            ):
                for filename in files:
                    if filename.lower() == "steam_api64.dll":
                        found.append(Path(root) / filename)

            self.log(f"steam_api64.dll search complete. Found {len(found)} file(s).")
            for path in found:
                self.log(f"Found DLL: {path}")
            self.root.after(0, self.dll_search_finished, found)

        except Exception as error:
            self.root.after(0, self.dll_search_failed, str(error))

    def dll_search_finished(self, found):
        self.stop_loading()
        self.steam_api64_paths = found

        if not found:
            self.status_label.config(
                text="Step 3 failed - steam_api64.dll not found."
            )
            self.root.after(500, self.choose_folder)
            return

        if len(found) > 1:
            self.status_label.config(
                text="Step 3 requires exactly one steam_api64.dll."
            )
            self.root.after(500, self.choose_folder)
            return

        dll_path = found[0]
        self.status_label.config(
            text="Step 3 complete - steam_api64.dll found."
        )

        self.root.after(250, self.start_step4)

    def dll_search_failed(self, error):
        self.stop_loading()
        self.status_label.config(text="Step 3 search failed.")
        messagebox.showerror(
            "Folder Search Error",
            "Unable to search the selected folder.\n\n" + error
        )

    # ========================================================
    # STEP 4 - GENERATE AND COPY STEAM INTERFACES
    # ========================================================

    def start_step4(self):
        if len(self.steam_api64_paths) != 1:
            return

        self.workflow_step = 4
        self.log("Step 4/5: copying steam_api64.dll to 02_STEP and generating interfaces.")
        self.start_loading("Step 4/5 - Generating steam_interfaces.txt...")

        threading.Thread(
            target=self.run_step4,
            daemon=True
        ).start()

    def run_step4(self):
        try:
            import shutil

            appid = self.current_appid
            dll_source = self.steam_api64_paths[0]
            _, step2, _, output_appid, settings_folder = self.get_workflow_paths(appid)

            temp_dll = step2 / "steam_api64.dll"
            temp_interfaces = step2 / "steam_interfaces.txt"
            generator = step2 / "generate_interfaces_x64.exe"

            if not generator.is_file():
                raise FileNotFoundError(
                    f"generate_interfaces_x64.exe was not found in:\n{generator}"
                )

            for path in (temp_dll, temp_interfaces):
                if path.exists():
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)

            shutil.copy2(dll_source, temp_dll)
            self.log(f"Copied DLL to: {temp_dll}")
            self.log(f"Running: generate_interfaces_x64.exe steam_api64.dll")
            self.log(f"Working directory: {step2}")

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [str(generator), "steam_api64.dll"],
                cwd=str(step2),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            self.log(f"generate_interfaces_x64.exe exited with code {result.returncode}.")
            self.log_command_output("generate_interfaces_x64.exe", result.stdout, result.stderr)

            if result.returncode != 0:
                details = result.stderr.strip() or result.stdout.strip() or "The interface generator returned an error."
                raise RuntimeError(details)

            if not temp_interfaces.is_file():
                raise FileNotFoundError(
                    "generate_interfaces_x64.exe finished, but steam_interfaces.txt was not created in 02_STEP."
                )

            settings_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_interfaces, settings_folder / "steam_interfaces.txt")
            self.log(f"Copied steam_interfaces.txt to: {settings_folder / 'steam_interfaces.txt'}")

            if temp_dll.exists():
                temp_dll.unlink()
            if temp_interfaces.exists():
                temp_interfaces.unlink()

            self.log("Deleted temporary files: 02_STEP/steam_api64.dll and 02_STEP/steam_interfaces.txt")
            self.log("Step 4 complete.")
            self.root.after(0, self.step4_finished, settings_folder / "steam_interfaces.txt")

        except subprocess.TimeoutExpired:
            self.root.after(0, self.workflow_failed, "Step 4 timed out while running generate_interfaces_x64.exe.")
        except Exception as error:
            self.root.after(0, self.workflow_failed, str(error))

    def step4_finished(self, interfaces_file):
        self.status_label.config(
            text="Step 4/5 complete - steam_interfaces.txt copied and 02_STEP cleaned."
        )
        self.root.after(250, self.start_step5)

    # ========================================================
    # STEP 5 - COPY FINAL FILES FROM 03_STEP
    # ========================================================

    def start_step5(self):
        self.workflow_step = 5
        self.log("Step 5/5: copying final steam_api64.dll and steam_settings from 03_STEP.")
        self.start_loading("Step 5/5 - Copying final files from 03_STEP...")

        threading.Thread(
            target=self.run_step5,
            daemon=True
        ).start()

    def run_step5(self):
        try:
            import shutil

            appid = self.current_appid
            _, _, step3, output_appid, _ = self.get_workflow_paths(appid)
            source_dll = step3 / "steam_api64.dll"
            source_settings = step3 / "steam_settings"
            destination_dll = output_appid / "steam_api64.dll"
            destination_settings = output_appid / "steam_settings"

            if not source_dll.is_file():
                raise FileNotFoundError(
                    f"steam_api64.dll was not found in 03_STEP:\n{source_dll}"
                )

            if not source_settings.is_dir():
                raise FileNotFoundError(
                    f"steam_settings folder was not found in 03_STEP:\n{source_settings}"
                )

            output_appid.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source_dll, destination_dll)
            self.log(f"Copied final DLL: {source_dll} -> {destination_dll}")
            shutil.copytree(
                source_settings,
                destination_settings,
                dirs_exist_ok=True
            )
            self.log(f"Copied/merged steam_settings: {source_settings} -> {destination_settings}")
            self.log("Existing files were overwritten/merged automatically.")

            self.root.after(
                0,
                self.start_final_deploy
            )

        except Exception as error:
            self.root.after(0, self.workflow_failed, str(error))

    # ========================================================
    # STEP 6 - BACK UP ORIGINAL DLL AND DEPLOY OUTPUT
    # ========================================================

    def start_final_deploy(self):
        self.workflow_step = 6
        self.log("Step 6/6: backing up the original steam_api64.dll and deploying the generated output.")
        self.start_loading("Step 6/6 - Deploying files to the game folder...")

        threading.Thread(
            target=self.run_final_deploy,
            daemon=True
        ).start()

    def run_final_deploy(self):
        try:
            import shutil

            appid = self.current_appid
            _, _, _, output_appid, _ = self.get_workflow_paths(appid)
            game_folder = self.selected_folder
            original_dll = self.steam_api64_paths[0]
            dll_folder = original_dll.parent
            backup_dll = dll_folder / "steam_api64.orig"

            if not game_folder or not game_folder.is_dir():
                raise FileNotFoundError(
                    "The selected game folder is no longer available:\n" + str(game_folder)
                )

            if not original_dll.is_file():
                raise FileNotFoundError(
                    "The original steam_api64.dll was not found:\n" + str(original_dll)
                )

            if not output_appid.is_dir():
                raise FileNotFoundError(
                    "The generated AppID output folder was not found:\n" + str(output_appid)
                )

            if backup_dll.exists():
                if backup_dll.is_file() or backup_dll.is_symlink():
                    backup_dll.unlink()
                elif backup_dll.is_dir():
                    shutil.rmtree(backup_dll)
                self.log(f"Removed existing backup: {backup_dll}")

            original_dll.rename(backup_dll)
            self.log(f"Renamed original DLL: {original_dll} -> {backup_dll}")

            for item in output_appid.iterdir():
                destination = dll_folder / item.name

                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                    self.log(f"Deployed folder: {item} -> {destination}")
                else:
                    shutil.copy2(item, destination)
                    self.log(f"Deployed file: {item} -> {destination}")

            self.log(f"Deployment source: {output_appid}")
            self.log(f"Original DLL folder: {dll_folder}")
            self.log(f"Deployment destination: {dll_folder}")
            self.log(f"Original DLL backup: {backup_dll}")
            self.root.after(0, self.workflow_finished, backup_dll, dll_folder)

        except Exception as error:
            self.root.after(0, self.workflow_failed, str(error))

    def workflow_finished(self, backup_dll, game_folder):
        self.log("Workflow completed successfully.")
        self.log(f"Original steam_api64.dll renamed to: {backup_dll}")
        self.log(f"AppID output deployed to: {game_folder}")
        self.log("FINISHED: Steam AppID setup and deployment completed successfully.")
        self.log("=" * 70)
        self.stop_loading()
        self.workflow_running = False
        self.workflow_step = None

        self.status_label.config(
            text="All steps completed successfully."
        )

    def workflow_failed(self, error):
        self.log(f"WORKFLOW FAILED: {error}")
        self.log("=" * 70)
        self.stop_loading()
        self.workflow_running = False
        self.workflow_step = None
        self.status_label.config(text="Workflow failed.")
        messagebox.showerror(
            "Workflow Error",
            "The workflow could not be completed.\n\n" + error
        )

    # ========================================================
    # SELECT GAME
    # ========================================================

    def select_game(self):

        selection = self.search_results.curselection()

        if not selection:

            messagebox.showwarning(
                "Select Game",
                "Please select a game from the search results."
            )

            return

        selected_text = self.search_results.get(
            selection[0]
        )

        match = re.search(
            r"\[AppID:\s*(\d+)\]",
            selected_text
        )

        if not match:

            messagebox.showerror(
                "Error",
                "Could not determine the AppID."
            )

            return

        appid = match.group(1)

        game_name = re.sub(
            r"\s*\[AppID:\s*\d+\]",
            "",
            selected_text
        ).strip()

        self.current_appid = appid
        self.current_game = game_name
        self.log(f"AppID selected: {appid}")
        self.log(f"Game selected: {game_name}")

        self.game_name_label.config(
            text=game_name
        )

        self.appid_label.config(
            text=appid
        )

        self.copy_button.config(
            state="normal"
        )

        self.steamdb_button.config(
            state="normal"
        )

        self.start_workflow()

        threading.Thread(
            target=self.download_banner,
            args=(appid,),
            daemon=True
        ).start()

    # ========================================================
    # DOWNLOAD BANNER
    # ========================================================

    def download_banner(self, appid):

        try:

            url = (
                "https://shared.fastly.steamstatic.com/"
                "store_item_assets/steam/apps/"
                f"{appid}/header.jpg"
            )

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64)"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=15
            ) as response:

                data = response.read()

            self.root.after(
                0,
                self.show_banner,
                data
            )

        except Exception:

            self.root.after(
                0,
                self.banner_failed
            )

    # ========================================================
    # SHOW BANNER
    # ========================================================

    def show_banner(self, data):

        try:

            image = Image.open(
                BytesIO(data)
            ).convert("RGB")

            self.banner_image = image

            if self.banner_frame is None:

                self.banner_frame = tk.Frame(
                    self.body,
                    bg=BG
                )

                self.banner_frame.pack(
                    fill="x",
                    pady=(6, 8),
                    before=self.log_title
                )

                self.banner_label = tk.Label(
                    self.banner_frame,
                    bg="#151515"
                )

                self.banner_label.pack(fill="x")

            self.update_banner()

            if not self.workflow_running:
                self.status_label.config(
                    text="Game selected successfully."
                )

        except Exception:

            self.banner_failed()

    # ========================================================
    # UPDATE BANNER
    # ========================================================

    def update_banner(self):

        if self.banner_image is None:
            return

        if self.banner_label is None:
            return

        width = self.body_width
        height = int(width * 215 / 460)

        image = self.banner_image.resize(
            (width, height),
            Image.Resampling.LANCZOS
        )

        self.banner_photo = ImageTk.PhotoImage(
            image
        )

        self.banner_label.config(
            image=self.banner_photo,
            text=""
        )

    # ========================================================
    # BANNER FAILED
    # ========================================================

    def banner_failed(self):

        if self.banner_frame is not None:
            self.banner_frame.destroy()
            self.banner_frame = None
            self.banner_label = None

        if not self.workflow_running:
            self.status_label.config(
                text="Game selected, but banner unavailable."
            )

    # ========================================================
    # COPY APPID
    # ========================================================

    def copy_appid(self):

        if not self.current_appid:
            return

        self.root.clipboard_clear()

        self.root.clipboard_append(
            self.current_appid
        )

        self.root.update()

        self.status_label.config(
            text="AppID copied to clipboard."
        )

    # ========================================================
    # OPEN STEAMDB
    # ========================================================

    def open_steamdb(self):

        if not self.current_appid:
            return

        url = (
            "https://steamdb.info/app/"
            + self.current_appid
            + "/"
        )

        webbrowser.open(
            url
        )

        self.status_label.config(
            text="SteamDB opened."
        )


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = SteamAppIDFinder(
        root
    )

    root.mainloop()


# PyInstaller build (Windows):
# pyinstaller --clean --noconfirm --onefile --windowed --name "Steam Emulator Setup" --icon="app_icon.ico" --add-data "app_icon.ico;." "Steam Emulator Setup.py"
