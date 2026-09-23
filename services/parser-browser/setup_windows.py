"""Self-contained per-user installer, bundled with the built application."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import queue


def install(payload, report):
    manifest_bytes = (payload / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    revision = hashlib.sha256(manifest_bytes).hexdigest()[:16]
    target = Path(os.environ['LOCALAPPDATA']) / 'AnalyticsPlatform' / 'TaraWorker' / revision
    target.mkdir(parents=True, exist_ok=True)
    for name, checksum in manifest.items():
        source = payload / 'app' / name
        dest = target / name
        if source.resolve().is_relative_to((payload / 'app').resolve()) is False or not dest.resolve().is_relative_to(target.resolve()):
            raise ValueError('Invalid installation path')
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == checksum:
            continue
        if hashlib.sha256(source.read_bytes()).hexdigest() != checksum:
            raise ValueError('Повреждён установочный файл. Получите установщик заново.')
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + '.installing')
        shutil.copyfile(source, temporary)
        temporary.replace(dest)
    report('Создание ярлыков…')
    # Parameters travel through the environment, never through PowerShell source interpolation.
    env = os.environ.copy()
    env['TARA_INSTALL_EXE'] = str(target / 'TaraWorker.exe')
    script = """
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $folder 'Tara Worker.lnk'))
    $shortcut.TargetPath = $env:TARA_INSTALL_EXE
    $shortcut.WorkingDirectory = Split-Path -LiteralPath $env:TARA_INSTALL_EXE
    $shortcut.Description = 'Tara Windows executor'
    $shortcut.Save()
}
"""
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                   env=env, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return target


def main():
    root = tk.Tk()
    root.title('Установка исполнителя Тары')
    root.geometry('560x230')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Исполнитель Тары', font=('Segoe UI', 14)).pack(anchor='w')
    ttk.Label(frame, text='Установка для текущего пользователя, без прав администратора.\nPython и библиотеки включены. Chromium подготовится при подключении.\nСуществующие настройки и данные сохраняются.', wraplength=520).pack(pady=12)
    status = tk.StringVar(value='Закройте приложение исполнителя перед обновлением.')
    ttk.Label(frame, textvariable=status, wraplength=520).pack()
    events = queue.Queue()
    running = False
    def work():
        try:
            payload = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'installer_payload'
            install(payload, lambda text: events.put(('progress', text)))
            events.put(('done', 'Готово. Запускайте ярлык Tara Worker на рабочем столе.'))
        except Exception as exc:
            events.put(('error', f'Установка не завершена: {type(exc).__name__}. Проверьте доступ к папке и закройте исполнитель.'))
    def start():
        nonlocal running
        running = True
        button.configure(state='disabled')
        status.set('Проверка и установка файлов…')
        threading.Thread(target=work, daemon=False).start()
    def poll():
        nonlocal running
        try:
            while True:
                kind, text = events.get_nowait()
                status.set(text)
                if kind != 'progress':
                    running = False
                    button.configure(state='normal', text='Закрыть' if kind == 'done' else 'Повторить', command=root.destroy if kind == 'done' else start)
        except queue.Empty:
            pass
        root.after(150, poll)
    button = ttk.Button(frame, text='Установить', command=start)
    button.pack(pady=12)
    root.protocol('WM_DELETE_WINDOW', lambda: messagebox.showinfo('Установка', 'Дождитесь окончания установки.') if running else root.destroy())
    root.after(150, poll)
    root.mainloop()


if __name__ == '__main__':
    main()
