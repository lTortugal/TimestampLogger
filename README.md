
[README (1).md](https://github.com/user-attachments/files/33184870/README.1.md)
# ⏱️ TimestampLogger

> **Автоматическая фиксация таймкодов при паузе на YouTube и в медиаплеерах Windows.**
> *Auto-pause timestamp logger for YouTube and Windows desktop media players.*

[![Release](https://img.shields.io/github/v/release/lTortugal/TimestampLogger?color=blue&label=Download%20EXE)](https://github.com/lTortugal/TimestampLogger/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue)](https://github.com/lTortugal/TimestampLogger)

[Русский](#русский) | [English](#english)

---

## Русский

**TimestampLogger** — утилита для Windows, которая автоматически сохраняет точные таймкоды, когда вы ставите воспроизведение на паузу. Работает через системный медиа-сервис Windows (GSMTC), поэтому получает название ролика, автора и позицию воспроизведения без установки расширений в браузер.

### ✨ Возможности

- 🎯 **Умный трекинг:** фиксирует событие ровно в момент паузы.
- 🔗 **Ссылки с таймкодом:** формирует прямую ссылку на момент видео (`&t=XXs`).
- 🖥️ **Любые плееры и браузеры:** Chrome, Firefox, Edge, Яндекс.Браузер, VLC, Spotify, PotPlayer и др.
- ⚙️ **Фильтры источников:** только браузеры, только плееры или все медиа.
- 🎛️ **GUI и трей:** отображение текущего трека/видео и сворачивание в системный трей Windows.
- 📝 **Логирование:** запись каждого события в текстовый файл с датой, названием и таймкодом.

### 📥 Скачать (.EXE)

1. Откройте раздел [Releases](https://github.com/lTortugal/TimestampLogger/releases).
2. Скачайте **`TimestampLogger.exe`** и запустите. Установка Python не требуется.

> ℹ️ При первом запуске Windows SmartScreen может показать предупреждение («Неизвестный издатель»). Нажмите **«Подробнее» → «Выполнить в любом случае»**. Это обычная реакция Windows на `.exe` без платного сертификата.

### 🛠️ Запуск из исходного кода

Требования: Windows 10/11, Python 3.10+

```bash
git clone https://github.com/lTortugal/TimestampLogger.git
cd TimestampLogger
pip install winsdk pystray pillow keyboard requests
python media_pause_tracker.py
```

Сборка своего `.exe`:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --icon icon.ico --add-data "icon.ico;." media_pause_tracker.py -n TimestampLogger
```

### 📄 Лицензия

Проект распространяется под лицензией MIT.

---

## English

**TimestampLogger** is a lightweight Windows utility that automatically logs media timestamps whenever you hit pause. Using Windows Native Media Controls (GSMTC), it tracks the current video or track and its playback position across web browsers and desktop media players, with no browser extensions required.

### ✨ Features

- 🎯 **Automatic Pause Detection:** captures the exact moment playback pauses.
- 🔗 **YouTube Deep Linking:** generates direct timestamped links (`&t=XXs`).
- 🖥️ **Universal Compatibility:** works with Chrome, Edge, Firefox, Brave, VLC, Spotify, PotPlayer, etc.
- ⚙️ **Media Filtering:** browser only, desktop player only, or all media.
- 🎛️ **Tray & Status GUI:** live display of the current media and active filter; minimizes to the system tray.
- 📝 **Clean Log File:** appends formatted timestamps, titles and channel names to a local log file.

### 📥 Download (.EXE)

1. Go to [Releases](https://github.com/lTortugal/TimestampLogger/releases).
2. Download **`TimestampLogger.exe`** and run it. No Python installation needed.

> ℹ️ On first launch, Windows SmartScreen may show an "Unknown publisher" warning. Click **More info → Run anyway**. This is normal for any `.exe` without a paid code-signing certificate.

### 🛠️ Run from Source

Requirements: Windows 10/11, Python 3.10+

```bash
git clone https://github.com/lTortugal/TimestampLogger.git
cd TimestampLogger
pip install winsdk pystray pillow keyboard requests
python media_pause_tracker.py
```

Build a standalone `.exe`:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --icon icon.ico --add-data "icon.ico;." media_pause_tracker.py -n TimestampLogger
```

### 📄 License

This project is licensed under the MIT License.
