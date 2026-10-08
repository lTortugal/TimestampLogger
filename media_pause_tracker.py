#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  YOUTUBE & MEDIA PLAYER AUTO-PAUSE TIMESTAMP LOGGER (WINDOWS 10 / 11)
=============================================================================
Автоматическая запись таймкодов при паузе видео на YouTube (в любых браузерах)
и в медиаплеерах (VLC, MPC-HC, PotPlayer) в папку:
timestamps

Включение/выключение отслеживания: клавиша [F9]
НЕ ТРЕБУЕТ C++ КОМПИЛЯТОРОВ И WINSNDK! (Работает на Python 3.10, 3.11, 3.12, 3.13)
"""

import os
import re
import sys
import time
import json
import threading
import subprocess
import winsound
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# ================= КОНФИГУРАЦИЯ =================
TARGET_FOLDER = r"timestamps"
TOGGLE_HOTKEY = "F9"
DEBOUNCE_SECONDS = 1.5
PLAY_SOUND = True
INCLUDE_DATE = True
TIME_FORMAT = "standard"  # standard, short, youtube_link, chapter, markdown
HTTP_PORT = 49152

# Фильтрация видео: Whitelist & Blacklist (сохраняется в filter_rules.json)
DEFAULT_FILTER_MODE = "all"
DEFAULT_WHITELIST = []
DEFAULT_BLACKLIST = []
# ===============================================

# Глобальное состояние
is_tracking_enabled = True
last_pause_time = 0
last_logged_position = -1
last_logged_title = ""
current_active_media = ""

def update_active_media(title: str):
    global current_active_media
    t = (title or "").strip()
    if t and t != current_active_media:
        current_active_media = t
        print(f"🎬 [МЕДИА]: {t}")

filter_mode = DEFAULT_FILTER_MODE
whitelist_items = list(DEFAULT_WHITELIST)
blacklist_items = list(DEFAULT_BLACKLIST)

# Поддержка горячей клавиши через библиотеку keyboard или встроенный ctypes
HAS_KEYBOARD = False
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    # Попытка фоновой установки легкой библиотеки keyboard (она не требует C++ компилятора)
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "keyboard"])
        import keyboard
        HAS_KEYBOARD = True
    except Exception:
        import ctypes
        HAS_KEYBOARD = False

def clean_filename(title: str) -> str:
    """Очищает название видео от недопустимых символов Windows"""
    if not title:
        title = "Неизвестное_видео"
    # Удаляем суффиксы браузеров и плееров
    title = re.sub(r'\s*-\s*(YouTube|Google Chrome|Microsoft Edge|Mozilla Firefox|Яндекс Браузер|VLC media player|Media Player Classic).*$', '', title, flags=re.I)
    # Заменяем запрещенные символы Windows: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/:*?"<>|]', '_', title).strip()
    return cleaned[:150] or "Без_названия"

def format_seconds(seconds: float) -> str:
    """Преобразует секунды в ЧЧ:ММ:СС или ММ:СС"""
    total_sec = max(0, int(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def play_beep(freq=1500, duration=100):
    # Полностью бесшумный режим (НОЛЬ ЗВУКОВ)
    pass

def get_app_dir() -> str:
    """Возвращает рабочую папку программы (где лежит скрипт или EXE)"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_target_directory() -> str:
    """Гарантированно возвращает и создает папку для сохранения таймкодов"""
    raw = TARGET_FOLDER.strip()
    if not raw or raw == "timestamps" or raw == r".	imestamps" or not os.path.isabs(raw):
        folder_name = raw if raw and raw != "." else "timestamps"
        target_path = os.path.join(get_app_dir(), folder_name)
    else:
        target_path = raw

    try:
        os.makedirs(target_path, exist_ok=True)
        return target_path
    except Exception:
        # Автоматический откат на папку timestamps рядом со скриптом
        fallback = os.path.join(get_app_dir(), "timestamps")
        try:
            os.makedirs(fallback, exist_ok=True)
            return fallback
        except Exception:
            return get_app_dir()

def get_filter_rules_file() -> str:
    return os.path.join(get_app_dir(), "filter_rules.json")

def load_filter_rules():
    global filter_mode, whitelist_items, blacklist_items
    config_file = get_filter_rules_file()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                filter_mode = data.get("filter_mode", filter_mode)
                whitelist_items = data.get("whitelist", whitelist_items)
                blacklist_items = data.get("blacklist", blacklist_items)
                return
        except Exception as e:
            print(f"⚠️ Ошибка чтения filter_rules.json: {e}")
    save_filter_rules()

def save_filter_rules():
    global filter_mode, whitelist_items, blacklist_items
    try:
        data = {
            "filter_mode": filter_mode,
            "whitelist": [w.strip() for w in whitelist_items if w.strip()],
            "blacklist": [b.strip() for b in blacklist_items if b.strip()]
        }
        with open(get_filter_rules_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения filter_rules.json: {e}")

def rule_matches(pattern: str, title: str, url: str) -> bool:
    """Умное сопоставление правила (путь к видеофайлу, папка, заголовок, URL)"""
    p = (pattern or "").strip().lower()
    if not p:
        return False
    t = (title or "").strip().lower()
    u = (url or "").strip().lower()

    # 1. Прямое совпадение подстроки в названии или URL
    if p in t or (u and p in u):
        return True

    # 2. Нормализация слэшей Windows и Unix (D:Видеоclip.mp4 -> d:/видео/clip.mp4)
    p_norm = p.replace(chr(92), '/')
    t_norm = t.replace(chr(92), '/')
    u_norm = u.replace(chr(92), '/')

    if p_norm in t_norm or (u_norm and p_norm in u_norm):
        return True

    # 3. Извлечение имени файла из пути (например: D:/Videos/Lesson1.mp4 -> lesson1.mp4)
    base = os.path.basename(p_norm)
    if base and len(base) > 1:
        if base in t or (u and base in u):
            return True
        # Без расширения файла (.mp4, .mkv и т.д.)
        stem = os.path.splitext(base)[0]
        if stem and len(stem) >= 3 and (stem in t or (u and stem in u)):
            return True

    # 4. Если в названии видео передан файл (например 'lesson.mp4'), а в правиле - папка ('D:/Videos')
    if ('/' in p_norm) and (t_norm in p_norm or (u_norm and u_norm in p_norm)):
        return True

    return False

def is_video_allowed(video_title: str, video_url: str = "") -> bool:
    """Проверяет видео по активному режиму (all, whitelist, blacklist)"""
    global filter_mode, whitelist_items, blacklist_items
    if filter_mode == "all":
        return True

    if filter_mode == "whitelist":
        clean_wl = [w.strip() for w in whitelist_items if w.strip()]
        if not clean_wl:
            return True  # Если белый список пуст, не блокируем
        for pattern in clean_wl:
            if rule_matches(pattern, video_title, video_url):
                return True
        print(f"⏭ [Whitelist] Пропущено (не в белом списке): '{video_title}'")
        return False

    elif filter_mode == "blacklist":
        clean_bl = [b.strip() for b in blacklist_items if b.strip()]
        for pattern in clean_bl:
            if rule_matches(pattern, video_title, video_url):
                print(f"🛑 [Blacklist] Заблокировано (в чёрном списке '{pattern}'): '{video_title}'")
                return False
        return True

    return True

def log_timestamp_to_file(video_title: str, position_sec: float, video_url: str = ""):
    """Создает файл (если нет) и ДОПИСЫВАЕТ таймкод С НОВОЙ СТРОКИ строго по порядку без перезаписи"""
    try:
        target_dir = get_target_directory()
        filename = clean_filename(video_title) + ".txt"
        filepath = os.path.join(target_dir, filename)
        
        timecode = format_seconds(position_sec)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Форматирование строки согласно настройкам
        if TIME_FORMAT == "short":
            line = f"{timecode}"
        elif TIME_FORMAT == "chapter":
            line = f"{timecode} Пауза"
        elif TIME_FORMAT == "youtube_link" and video_url:
            clean_url = video_url.split('&t=')[0]
            line = f"[{timecode}] {clean_url}&t={int(position_sec)}s"
        elif TIME_FORMAT == "markdown":
            if video_url:
                line = f"- [{timecode}]({video_url}&t={int(position_sec)}s)"
            else:
                line = f"- {timecode}"
        else:
            line = f"[{timecode}]"
            
        if INCLUDE_DATE:
            line += f"  (зафиксировано: {now_str})"
            
        # БЕЗ ПЕРЕЗАПИСИ (режим 'a' = append)
        # Каждый таймкод гарантированно пишется С НОВОЙ СТРОКИ по порядку
        file_is_new = not os.path.exists(filepath) or os.path.getsize(filepath) == 0
        
        with open(filepath, "a", encoding="utf-8") as f:
            if file_is_new:
                f.write(f"=== Таймкоды видео: {video_title} ===\n")
                if video_url:
                    f.write(f"Ссылка: {video_url}\n")
                f.write(f"Создан: {now_str}\n\n")
            # Строго каждый таймкод с новой строки
            f.write(f"{line}\n")
            f.flush()
            
        print(f"[✔ ЗАПИСАНО] {timecode} -> {filepath}")
    except Exception as e:
        print(f"❌ Ошибка записи в файл: {e}")

def handle_pause_event(video_title: str, position_sec: float, video_url: str = ""):
    global last_pause_time, last_logged_position, last_logged_title
    update_active_media(video_title)
    if not is_tracking_enabled:
        return

    # Проверка правил фильтрации Whitelist / Blacklist
    if not is_video_allowed(video_title, video_url):
        return
        
    current_time = time.time()
    if current_time - last_pause_time < DEBOUNCE_SECONDS:
        return
        
    # Защита от дублей при мгновенных повторах
    if abs(position_sec - last_logged_position) < 1.0 and video_title == last_logged_title:
        return
        
    last_pause_time = current_time
    last_logged_position = position_sec
    last_logged_title = video_title
    log_timestamp_to_file(video_title, position_sec, video_url)

def toggle_tracking():
    global is_tracking_enabled
    is_tracking_enabled = not is_tracking_enabled
    if is_tracking_enabled:
        print(f"\n🟢 [ВКЛЮЧЕНО] Отслеживание активно (Горячая клавиша: {TOGGLE_HOTKEY})")
    else:
        print(f"\n🔴 [ПАУЗА] Отслеживание приостановлено (Горячая клавиша: {TOGGLE_HOTKEY})")

# Локальный HTTP-сервер для мгновенного приема таймкодов из браузера/расширения
class LocalTimestampHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode('utf-8'))
            title = data.get('title', 'YouTube')
            pos = float(data.get('position', 0))
            url = data.get('url', '')
            update_active_media(title)
            handle_pause_event(title, pos, url)
        except Exception:
            pass
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass  # подавляем шум в консоли

def start_http_receiver():
    try:
        server = HTTPServer(('127.0.0.1', HTTP_PORT), LocalTimestampHandler)
        server.serve_forever()
    except Exception:
        pass

# Windows Job Object для автоматического уничтожения PowerShell ядром Windows при выходе
h_job = None
def init_windows_job():
    global h_job
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        h_job = kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return
            
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', wintypes.LARGE_INTEGER),
                ('PerJobUserTimeLimit', wintypes.LARGE_INTEGER),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('ReadOperationCount', ctypes.c_ulonglong),
                ('WriteOperationCount', ctypes.c_ulonglong),
                ('OtherOperationCount', ctypes.c_ulonglong),
                ('ReadTransferCount', ctypes.c_ulonglong),
                ('WriteTransferCount', ctypes.c_ulonglong),
                ('OtherTransferCount', ctypes.c_ulonglong),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryLimit', ctypes.c_size_t),
                ('PeakJobMemoryLimit', ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(h_job, 9, ctypes.byref(info), ctypes.sizeof(info))
    except Exception:
        h_job = None

# PowerShell WinRT слушатель Windows Media (работает без сторонних библиотек на Windows 10/11)
PS_SCRIPT = r"""
try {
    # ВАЖНО: изолируем текущую папку в TEMP, чтобы PowerShell НИКОГДА не удерживал папку скрипта
    [System.IO.Directory]::SetCurrentDirectory($env:TEMP)
    Set-Location -Path $env:TEMP
} catch {}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1
} | Select-Object -First 1

function AwaitTask($WinRtOp, $Type) {
    if (-not $WinRtOp) { return $null }
    try {
        $task = $asTaskMethod.MakeGenericMethod($Type).Invoke($null, @($WinRtOp))
        if ($task.Wait(3000)) {
            return $task.Result
        }
    } catch {}
    return $null
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionPlaybackStatus, Windows.Media, ContentType=WindowsRuntime] | Out-Null

$mgr = $null
$lastStatus = $null
$lastReportedTitle = ""

while ($true) {
    try {
        if (-not $mgr) {
            $mgrTask = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()
            $mgr = AwaitTask $mgrTask ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
        }
        if ($mgr) {
            $session = $mgr.GetCurrentSession()
            if ($session) {
                $status = $session.GetPlaybackInfo().PlaybackStatus
                $statusStr = if ($status) { $status.ToString() } else { "" }
                $lastStr = if ($lastStatus) { $lastStatus.ToString() } else { "" }
                
                # Получаем метаданные текущего воспроизводимого видео в реальном времени
                $propsTask = $session.TryGetMediaPropertiesAsync()
                $props = AwaitTask $propsTask ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
                $rawTitle = if ($props -and $props.Title) { $props.Title.Trim() } else { "" }

                # Если название изменилось (пользователь переключил видео), немедленно рапортуем
                if ($rawTitle -and $rawTitle -ne $lastReportedTitle) {
                    $lastReportedTitle = $rawTitle
                    $outMedia = @{ title = $rawTitle } | ConvertTo-Json -Compress
                    [Console]::WriteLine("ACTIVE_MEDIA:" + $outMedia)
                }
                
                # Фиксация события паузы видео/музыки
                if ($statusStr -eq 'Paused' -and ($lastStr -eq 'Playing' -or -not $lastStr)) {
                    $timeline = $session.GetTimelineProperties()
                    $title = if ($rawTitle) { $rawTitle } else { "YouTube" }
                    $pos = if ($timeline -and $timeline.Position) { $timeline.Position.TotalSeconds } else { 0 }
                    
                    $out = @{ title = $title; position = [math]::Round($pos, 1) } | ConvertTo-Json -Compress
                    [Console]::WriteLine("PAUSE_EVENT:" + $out)
                }
                $lastStatus = $status
            }
        }
    } catch {}
    Start-Sleep -Milliseconds 250
}
"""

ps_proc = None

def stop_all_processes():
    """Чистое и надежное закрытие фонового процесса powershell без блокировки папок на диске"""
    global ps_proc
    if ps_proc:
        pid = ps_proc.pid
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass
        try:
            ps_proc.terminate()
            ps_proc.kill()
        except Exception:
            pass
        ps_proc = None

def start_powershell_media_listener():
    global ps_proc, h_job
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-Command", PS_SCRIPT
    ]
    creationflags = 0x08000000 if os.name == 'nt' else 0
    # ВАЖНО: cwd = TEMP, чтобы PowerShell НИКОГДА не блокировал рабочую папку программы!
    temp_dir = os.environ.get("TEMP", r"C:WindowsTemp")
    
    while True:
        try:
            ps_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                cwd=temp_dir,
                creationflags=creationflags
            )
            # Привязываем процесс PowerShell к Job Object (гарантия авто-убийства ядром ОС)
            if h_job and os.name == 'nt' and hasattr(ps_proc, '_handle'):
                try:
                    import ctypes
                    ctypes.windll.kernel32.AssignProcessToJobObject(h_job, ps_proc._handle)
                except Exception:
                    pass

            for line in iter(ps_proc.stdout.readline, ''):
                line = line.strip()
                if line.startswith("ACTIVE_MEDIA:"):
                    json_str = line[len("ACTIVE_MEDIA:"):]
                    try:
                        data = json.loads(json_str)
                        m_title = data.get("title", "").strip()
                        if m_title:
                            update_active_media(m_title)
                    except Exception:
                        pass
                elif line.startswith("PAUSE_EVENT:"):
                    json_str = line[len("PAUSE_EVENT:"):]
                    try:
                        data = json.loads(json_str)
                        m_title = data.get("title", "Медиа").strip()
                        update_active_media(m_title)
                        handle_pause_event(m_title, float(data.get("position", 0)))
                    except Exception:
                        pass
        except Exception as e:
            print(f"⚠️ Служба Windows Media: {e}")
        time.sleep(1)

# Фоновый слушатель горячей клавиши F9 через ctypes (если нет модуля keyboard)
def ctypes_hotkey_listener():
    import ctypes
    VK_F9 = 0x78
    was_down = False
    while True:
        try:
            state = ctypes.windll.user32.GetAsyncKeyState(VK_F9)
            is_down = bool(state & 0x8000)
            if is_down and not was_down:
                toggle_tracking()
            was_down = is_down
            time.sleep(0.05)
        except Exception:
            time.sleep(0.2)

def get_resource_path(relative_name):
    """Поиск пути к ресурсу внутри собранного PyInstaller EXE или в рабочей папке"""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base_path, relative_name)
    if os.path.exists(full_path):
        return full_path
    curr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_name)
    if os.path.exists(curr_path):
        return curr_path
    return None

gui_root = None
gui_lock = threading.Lock()

def open_filter_gui():
    """Открывает графическое окно (GUI) настройки Whitelist и Blacklist"""
    global gui_root
    with gui_lock:
        if gui_root is not None:
            try:
                gui_root.deiconify()
                gui_root.lift()
                gui_root.focus_force()
                return
            except Exception:
                gui_root = None
    threading.Thread(target=_run_tkinter_gui, daemon=True).start()

def _run_tkinter_gui():
    global gui_root, filter_mode, whitelist_items, blacklist_items, last_logged_title, current_active_media
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except Exception:
        # Резервный режим: открываем JSON файл настроек в блокноте
        if os.name == 'nt':
            try:
                save_filter_rules()
                os.startfile(get_filter_rules_file())
            except Exception:
                pass
        return

    root = tk.Tk()
    with gui_lock:
        gui_root = root

    root.title("Timestamp Logger — Настройки фильтрации (Whitelist & Blacklist)")
    root.geometry("680x760")
    root.minsize(580, 620)
    root.configure(bg="#0b0f19")

    # Иконка окна (если есть icon.ico)
    icon_p = get_resource_path("icon.ico")
    if icon_p and os.path.exists(icon_p):
        try:
            root.iconbitmap(icon_p)
        except Exception:
            pass

    # Верхний заголовок
    header_frame = tk.Frame(root, bg="#111827", padx=16, pady=12, highlightbackground="#1f2937", highlightthickness=1)
    header_frame.pack(fill="x", padx=14, pady=(14, 10))

    title_lbl = tk.Label(header_frame, text="⚙️ Настройки фильтрации видео (Whitelist & Blacklist)", font=("Segoe UI", 13, "bold"), fg="#f8fafc", bg="#111827")
    title_lbl.pack(anchor="w")

    subtitle_lbl = tk.Label(header_frame, text="Укажите пути к видеофайлам, папки, названия или ссылки YouTube, для которых сохранять или игнорировать паузы", font=("Segoe UI", 9), fg="#94a3b8", bg="#111827")
    subtitle_lbl.pack(anchor="w", pady=(3, 0))

    # Информационный блок текущего активного режима работы фильтра
    mode_frame = tk.Frame(root, bg="#111827", padx=16, pady=10, highlightbackground="#1f2937", highlightthickness=1)
    mode_frame.pack(fill="x", padx=14, pady=6)

    mode_info_map = {
        "all": ("⚪ Все видео (без ограничений)", "#38bdf8", "Записывать таймкоды для всех воспроизводимых видео без фильтрации"),
        "whitelist": ("🟢 Whitelist (Белый список)", "#34d399", "Сохранять таймкоды ТОЛЬКО для видео из белого списка"),
        "blacklist": ("🔴 Blacklist (Чёрный список)", "#f87171", "Сохранять таймкоды для всех видео, КРОМЕ указанных в чёрном списке")
    }
    cur_title, cur_color, cur_desc = mode_info_map.get(filter_mode, ("⚪ Все видео", "#38bdf8", ""))

    mode_lbl_row = tk.Frame(mode_frame, bg="#111827")
    mode_lbl_row.pack(fill="x")

    lbl_prefix = tk.Label(mode_lbl_row, text="Текущий активный режим фильтра:", font=("Segoe UI", 9), fg="#94a3b8", bg="#111827")
    lbl_prefix.pack(side="left")

    lbl_badge = tk.Label(mode_lbl_row, text=f"  {cur_title}  ", font=("Segoe UI", 10, "bold"), fg=cur_color, bg="#1e293b", padx=6, pady=2)
    lbl_badge.pack(side="left", padx=8)

    lbl_desc = tk.Label(mode_frame, text=f"{cur_desc} • (Смена режима: правый клик по иконке в трее)", font=("Segoe UI", 8), fg="#64748b", bg="#111827")
    lbl_desc.pack(anchor="w", pady=(4, 0))

    # Панель с текущим активным видео (живое динамическое обновление в реальном времени)
    current_media_frame = tk.Frame(root, bg="#0f172a", padx=12, pady=8, highlightbackground="#1e293b", highlightthickness=1)
    current_media_frame.pack(fill="x", padx=14, pady=4)

    cur_lbl = tk.Label(current_media_frame, text="🎬 Текущее медиа: Ожидание воспроизведения видео...", font=("Segoe UI", 9, "italic"), fg="#cbd5e1", bg="#0f172a")
    cur_lbl.pack(side="left")

    def get_display_media():
        global current_active_media, last_logged_title
        return (current_active_media or last_logged_title or "").strip()

    def poll_active_media_gui():
        try:
            media = get_display_media()
            if media:
                short_text = (media[:65] + "...") if len(media) > 65 else media
                cur_lbl.config(text=f"🎬 Текущее медиа: {short_text}", fg="#38bdf8")
            else:
                cur_lbl.config(text="🎬 Текущее медиа: Ожидание воспроизведения видео...", fg="#94a3b8")
        except Exception:
            pass
        try:
            root.after(300, poll_active_media_gui)
        except Exception:
            pass

    poll_active_media_gui()

    # Стилизация вкладок
    style = ttk.Style()
    style.theme_use("default")
    style.configure("TNotebook", background="#0b0f19", borderwidth=0)
    style.configure("TNotebook.Tab", background="#1e293b", foreground="#94a3b8", font=("Segoe UI", 9, "bold"), padding=[16, 6])
    style.map("TNotebook.Tab", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=14, pady=8)

    # ---------------- Вспомогательные функции для списков ----------------
    def append_to_text(widget, line_text):
        if not line_text:
            return
        current = widget.get("1.0", tk.END).strip()
        lines = [l.strip() for l in current.split("\n") if l.strip()]
        if line_text not in lines:
            if current:
                widget.insert(tk.END, "\n" + line_text)
            else:
                widget.insert(tk.END, line_text)
            widget.see(tk.END)

    # 1. Вкладка Whitelist
    tab_wl = tk.Frame(notebook, bg="#0f172a", padx=10, pady=10)
    notebook.add(tab_wl, text=" 🟢 Белый список (Whitelist) ")

    lbl_wl_hint = tk.Label(
        tab_wl,
        text="Записывать таймкоды ТОЛЬКО если путь к файлу, название или ссылка совпадают (по одной записи на строку):",
        font=("Segoe UI", 8),
        fg="#94a3b8",
        bg="#0f172a",
        wraplength=620,
        justify="left"
    )
    lbl_wl_hint.pack(anchor="w", pady=(0, 6))

    # Тулбар действий Whitelist
    wl_tools = tk.Frame(tab_wl, bg="#0f172a")
    wl_tools.pack(fill="x", pady=(0, 6))

    wl_text_frame = tk.Frame(tab_wl, bg="#0f172a")
    wl_text_frame.pack(fill="both", expand=True)

    wl_scrollbar = tk.Scrollbar(wl_text_frame)
    wl_scrollbar.pack(side="right", fill="y")

    wl_text = tk.Text(
        wl_text_frame,
        bg="#020617",
        fg="#38bdf8",
        insertbackground="#38bdf8",
        font=("Consolas", 10),
        yscrollcommand=wl_scrollbar.set,
        relief="flat",
        padx=8,
        pady=8,
        highlightbackground="#1e293b",
        highlightthickness=1
    )
    wl_text.pack(side="left", fill="both", expand=True)
    wl_scrollbar.config(command=wl_text.yview)
    wl_text.insert("1.0", "\n".join(whitelist_items))

    def on_wl_browse_file():
        try:
            files = filedialog.askopenfilenames(
                title="Выберите видеофайлы для добавления в Whitelist",
                filetypes=[
                    ("Видео файлы", "*.mp4;*.mkv;*.webm;*.avi;*.mov;*.wmv;*.flv;*.ts;*.m4v"),
                    ("Все файлы", "*.*")
                ]
            )
            if files:
                for f in files:
                    append_to_text(wl_text, os.path.normpath(f))
                status_lbl.config(text=f"✔ Добавлено видеофайлов в Whitelist: {len(files)}", fg="#34d399")
        except Exception as e:
            print(f"Ошибка выбора файла: {e}")

    def on_wl_browse_dir():
        try:
            d = filedialog.askdirectory(title="Выберите папку с видео для Whitelist")
            if d:
                append_to_text(wl_text, os.path.normpath(d))
                status_lbl.config(text=f"✔ Папка добавлена в Whitelist: {os.path.basename(d)}", fg="#34d399")
        except Exception as e:
            print(f"Ошибка выбора папки: {e}")

    def on_wl_clear():
        wl_text.delete("1.0", tk.END)
        status_lbl.config(text="Whitelist очищен", fg="#94a3b8")

    def on_wl_paste_clip():
        try:
            clip = root.clipboard_get()
            if clip:
                for line in clip.splitlines():
                    if line.strip():
                        append_to_text(wl_text, line.strip())
                status_lbl.config(text="Вставлено из буфера обмена", fg="#38bdf8")
        except Exception:
            pass

    btn_wl_file = tk.Button(wl_tools, text="➕ Выбрать видеофайл...", command=on_wl_browse_file, font=("Segoe UI", 8, "bold"), fg="#ffffff", bg="#0369a1", activebackground="#0284c7", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_wl_file.pack(side="left", padx=(0, 4))

    btn_wl_dir = tk.Button(wl_tools, text="📁 Выбрать папку...", command=on_wl_browse_dir, font=("Segoe UI", 8), fg="#cbd5e1", bg="#1e293b", activebackground="#334155", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_wl_dir.pack(side="left", padx=4)

    btn_wl_paste = tk.Button(wl_tools, text="📋 Вставить", command=on_wl_paste_clip, font=("Segoe UI", 8), fg="#cbd5e1", bg="#1e293b", activebackground="#334155", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_wl_paste.pack(side="left", padx=4)

    btn_wl_clear = tk.Button(wl_tools, text="🧹 Очистить", command=on_wl_clear, font=("Segoe UI", 8), fg="#94a3b8", bg="#0f172a", activebackground="#1e293b", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_wl_clear.pack(side="right")

    # 2. Вкладка Blacklist
    tab_bl = tk.Frame(notebook, bg="#0f172a", padx=10, pady=10)
    notebook.add(tab_bl, text=" 🔴 Чёрный список (Blacklist) ")

    lbl_bl_hint = tk.Label(
        tab_bl,
        text="Игнорировать и НЕ сохранять таймкоды, если видео или путь содержит эти записи (по одной записи на строку):",
        font=("Segoe UI", 8),
        fg="#94a3b8",
        bg="#0f172a",
        wraplength=620,
        justify="left"
    )
    lbl_bl_hint.pack(anchor="w", pady=(0, 6))

    # Тулбар действий Blacklist
    bl_tools = tk.Frame(tab_bl, bg="#0f172a")
    bl_tools.pack(fill="x", pady=(0, 6))

    bl_text_frame = tk.Frame(tab_bl, bg="#0f172a")
    bl_text_frame.pack(fill="both", expand=True)

    bl_scrollbar = tk.Scrollbar(bl_text_frame)
    bl_scrollbar.pack(side="right", fill="y")

    bl_text = tk.Text(
        bl_text_frame,
        bg="#020617",
        fg="#f87171",
        insertbackground="#f87171",
        font=("Consolas", 10),
        yscrollcommand=bl_scrollbar.set,
        relief="flat",
        padx=8,
        pady=8,
        highlightbackground="#1e293b",
        highlightthickness=1
    )
    bl_text.pack(side="left", fill="both", expand=True)
    bl_scrollbar.config(command=bl_text.yview)
    bl_text.insert("1.0", "\n".join(blacklist_items))

    def on_bl_browse_file():
        try:
            files = filedialog.askopenfilenames(
                title="Выберите видеофайлы для добавления в Blacklist",
                filetypes=[
                    ("Видео файлы", "*.mp4;*.mkv;*.webm;*.avi;*.mov;*.wmv;*.flv;*.ts;*.m4v"),
                    ("Все файлы", "*.*")
                ]
            )
            if files:
                for f in files:
                    append_to_text(bl_text, os.path.normpath(f))
                status_lbl.config(text=f"✔ Добавлено видеофайлов в Blacklist: {len(files)}", fg="#f87171")
        except Exception as e:
            print(f"Ошибка выбора файла: {e}")

    def on_bl_browse_dir():
        try:
            d = filedialog.askdirectory(title="Выберите папку с видео для Blacklist")
            if d:
                append_to_text(bl_text, os.path.normpath(d))
                status_lbl.config(text=f"✔ Папка добавлена в Blacklist: {os.path.basename(d)}", fg="#f87171")
        except Exception as e:
            print(f"Ошибка выбора папки: {e}")

    def on_bl_clear():
        bl_text.delete("1.0", tk.END)
        status_lbl.config(text="Blacklist очищен", fg="#94a3b8")

    def on_bl_paste_clip():
        try:
            clip = root.clipboard_get()
            if clip:
                for line in clip.splitlines():
                    if line.strip():
                        append_to_text(bl_text, line.strip())
                status_lbl.config(text="Вставлено из буфера обмена", fg="#f87171")
        except Exception:
            pass

    btn_bl_file = tk.Button(bl_tools, text="➕ Выбрать видеофайл...", command=on_bl_browse_file, font=("Segoe UI", 8, "bold"), fg="#ffffff", bg="#b91c1c", activebackground="#dc2626", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_bl_file.pack(side="left", padx=(0, 4))

    btn_bl_dir = tk.Button(bl_tools, text="📁 Выбрать папку...", command=on_bl_browse_dir, font=("Segoe UI", 8), fg="#cbd5e1", bg="#1e293b", activebackground="#334155", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_bl_dir.pack(side="left", padx=4)

    btn_bl_paste = tk.Button(bl_tools, text="📋 Вставить", command=on_bl_paste_clip, font=("Segoe UI", 8), fg="#cbd5e1", bg="#1e293b", activebackground="#334155", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_bl_paste.pack(side="left", padx=4)

    btn_bl_clear = tk.Button(bl_tools, text="🧹 Очистить", command=on_bl_clear, font=("Segoe UI", 8), fg="#94a3b8", bg="#0f172a", activebackground="#1e293b", activeforeground="#ffffff", relief="flat", padx=8, pady=4, cursor="hand2")
    btn_bl_clear.pack(side="right")

    # Быстрые кнопки добавления текущего видео в шапке
    def add_current_to_wl():
        media = get_display_media()
        if media:
            append_to_text(wl_text, media)
            notebook.select(0)
            status_lbl.config(text=f"✔ Добавлено в Whitelist: {media[:40]}", fg="#34d399")

    def add_current_to_bl():
        media = get_display_media()
        if media:
            append_to_text(bl_text, media)
            notebook.select(1)
            status_lbl.config(text=f"✔ Добавлено в Blacklist: {media[:40]}", fg="#f87171")

    btn_add_cur_bl = tk.Button(current_media_frame, text="➕ В Blacklist", command=add_current_to_bl, font=("Segoe UI", 8), fg="#fca5a5", bg="#7f1d1d", activebackground="#991b1b", relief="flat", padx=8, pady=2, cursor="hand2")
    btn_add_cur_bl.pack(side="right", padx=(4, 0))

    btn_add_cur_wl = tk.Button(current_media_frame, text="➕ В Whitelist", command=add_current_to_wl, font=("Segoe UI", 8), fg="#a7f3d0", bg="#065f46", activebackground="#047857", relief="flat", padx=8, pady=2, cursor="hand2")
    btn_add_cur_wl.pack(side="right")

    # Переключаем активную вкладку в зависимости от текущего режима
    if filter_mode == "blacklist":
        notebook.select(1)
    else:
        notebook.select(0)

    # Статусная строка обратной связи
    status_lbl = tk.Label(root, text="", font=("Segoe UI", 9, "bold"), fg="#34d399", bg="#0b0f19")
    status_lbl.pack(pady=3)

    def on_save_apply():
        global filter_mode, whitelist_items, blacklist_items
        raw_wl = wl_text.get("1.0", tk.END).strip().split("\n")
        raw_bl = bl_text.get("1.0", tk.END).strip().split("\n")
        
        whitelist_items = [w.strip() for w in raw_wl if w.strip()]
        blacklist_items = [b.strip() for b in raw_bl if b.strip()]
        save_filter_rules()

        mode_names = {"all": "Все видео (без фильтра)", "whitelist": "Whitelist (Белый список)", "blacklist": "Blacklist (Чёрный список)"}
        status_lbl.config(text=f"✔ Списки сохранены! Текущий режим: {mode_names.get(filter_mode, filter_mode)}", fg="#34d399")
        print(f"⚙️ [GUI] Списки исключений сохранены: активный режим={filter_mode}, whitelist={len(whitelist_items)}, blacklist={len(blacklist_items)}")

    def on_open_folder_click():
        target_dir = get_target_directory()
        if os.name == 'nt':
            os.startfile(target_dir)

    def on_close():
        global gui_root
        try:
            on_save_apply()
        except Exception:
            pass
        with gui_lock:
            gui_root = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # Нижняя панель с кнопками
    btn_bar = tk.Frame(root, bg="#0b0f19", padx=14, pady=12)
    btn_bar.pack(fill="x")

    save_btn = tk.Button(
        btn_bar,
        text="💾 Сохранить и применить",
        command=on_save_apply,
        font=("Segoe UI", 10, "bold"),
        fg="#ffffff",
        bg="#059669",
        activebackground="#10b981",
        activeforeground="#ffffff",
        relief="flat",
        padx=18,
        pady=8,
        cursor="hand2"
    )
    save_btn.pack(side="left")

    folder_btn = tk.Button(
        btn_bar,
        text="📁 Папка timestamps",
        command=on_open_folder_click,
        font=("Segoe UI", 9),
        fg="#cbd5e1",
        bg="#1e293b",
        activebackground="#334155",
        activeforeground="#ffffff",
        relief="flat",
        padx=14,
        pady=8,
        cursor="hand2"
    )
    folder_btn.pack(side="left", padx=10)

    close_btn = tk.Button(
        btn_bar,
        text="Закрыть",
        command=on_close,
        font=("Segoe UI", 9),
        fg="#94a3b8",
        bg="#0f172a",
        activebackground="#1e293b",
        activeforeground="#ffffff",
        relief="flat",
        padx=14,
        pady=8,
        cursor="hand2"
    )
    close_btn.pack(side="right")

    # Выводим на передний план
    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)
    root.focus_force()

    root.mainloop()

def run_tray_icon():
    """Запуск иконки в системном трее Windows (рядом с часами)"""
    try:
        import pystray
        from PIL import Image, ImageDraw

        image = None
        # Проверяем наличие фирменной иконки (icon.ico или icon.png)
        icon_path = get_resource_path("icon.ico") or get_resource_path("icon.png")
        if icon_path and os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                image.load()
            except Exception:
                pass

        # Если иконки нет в файлах, генерируем стильную неоновую иконку
        if not image:
            image = Image.new('RGBA', (64, 64), (16, 20, 36, 255))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle([4, 4, 60, 60], radius=14, fill='#13182b', outline='#ef4444', width=3)
            # Знак паузы
            draw.rounded_rectangle([22, 18, 28, 46], radius=2, fill='#ffffff')
            draw.rounded_rectangle([36, 18, 42, 46], radius=2, fill='#ffffff')

        def on_open_folder(icon, item):
            try:
                target_dir = get_target_directory()
                if os.name == 'nt':
                    os.startfile(target_dir)
            except Exception:
                pass

        def on_toggle_click(icon, item):
            toggle_tracking()

        def set_mode_from_tray(new_mode):
            global filter_mode
            filter_mode = new_mode
            save_filter_rules()
            mode_names = {"all": "Все видео (без фильтра)", "whitelist": "Whitelist (Белый список)", "blacklist": "Blacklist (Чёрный список)"}
            print(f"🔄 Режим фильтрации изменен на: {mode_names.get(filter_mode, filter_mode)}")

        def on_exit_app(icon, item):
            stop_all_processes()
            try:
                icon.visible = False
                icon.stop()
            except Exception:
                pass
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("⚙️ Фильтры: Whitelist & Blacklist (GUI)...", lambda icon, item: open_filter_gui(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⚪ Все видео (без ограничений)", lambda icon, item: set_mode_from_tray("all"), checked=lambda item: filter_mode == "all"),
            pystray.MenuItem("🟢 Whitelist (Только разрешенные)", lambda icon, item: set_mode_from_tray("whitelist"), checked=lambda item: filter_mode == "whitelist"),
            pystray.MenuItem("🔴 Blacklist (Исключить запрещенные)", lambda icon, item: set_mode_from_tray("blacklist"), checked=lambda item: filter_mode == "blacklist"),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📁 Открыть папку timestamps", on_open_folder),
            pystray.MenuItem(lambda text: f"Отслеживание: {'ВКЛ' if is_tracking_enabled else 'ПАУЗА'} ({TOGGLE_HOTKEY})", on_toggle_click),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Выход (закрыть программу)", on_exit_app)
        )

        target_dir_name = os.path.basename(get_target_directory()) or "timestamps"
        icon = pystray.Icon("TimestampLogger", image, f"Timestamp Logger ({target_dir_name})", menu)
        icon.run()
    except Exception:
        while True:
            time.sleep(1)

def main():
    import atexit
    import signal

    init_windows_job()
    atexit.register(stop_all_processes)

    def sig_handler(sig, frame):
        stop_all_processes()
        os._exit(0)

    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except Exception:
        pass

    # 0. Загружаем правила фильтрации (whitelist / blacklist) и создаем папку timestamps
    load_filter_rules()
    target_dir = get_target_directory()
    print("=" * 60)
    print("  YouTube & Media Pause Timestamp Logger запущен!")
    print(f"  Папка сохранения: {target_dir}")
    print(f"  Горячая клавиша: [{TOGGLE_HOTKEY}]")
    print(f"  Режим фильтрации: {filter_mode.upper()} (GUI доступен через трей)")
    print("=" * 60)

    # 1. Автоматически скрываем черное окно консоли и задаем AppUserModelID для иконки
    if os.name == 'nt':
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YouTube.TimestampLogger.App.1.0")
        except Exception:
            pass

    # 2. Регистрация горячей клавиши F9
    if HAS_KEYBOARD:
        try:
            keyboard.add_hotkey(TOGGLE_HOTKEY, toggle_tracking)
        except Exception:
            threading.Thread(target=ctypes_hotkey_listener, daemon=True).start()
    else:
        threading.Thread(target=ctypes_hotkey_listener, daemon=True).start()

    # 3. Запуск фонового HTTP моста
    threading.Thread(target=start_http_receiver, daemon=True).start()

    # 4. Запуск системного отслеживания медиаплееров и браузеров через PowerShell WinRT
    threading.Thread(target=start_powershell_media_listener, daemon=True).start()

    # 5. Иконка в системном трее Windows (основной поток)
    run_tray_icon()

if __name__ == "__main__":
    main()
