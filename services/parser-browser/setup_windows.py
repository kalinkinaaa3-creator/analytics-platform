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
import ctypes
from ctypes import wintypes
import uuid


def create_shortcut(executable, destination):
    """Use Windows shell COM directly, without PowerShell or its execution policies."""
    ole = ctypes.OleDLL('ole32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    initialized = ole.CoInitializeEx(None, 2)
    link = ctypes.c_void_p()
    persist = ctypes.c_void_p()
    def guid(value):
        return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)
    def method(pointer, index, *args):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *args)(table[index])
    def check(result):
        if result < 0:
            raise OSError(f'Windows Shell HRESULT 0x{result & 0xffffffff:08X}')
    try:
        ole.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        check(ole.CoCreateInstance(guid('00021401-0000-0000-C000-000000000046'), None, 1,
                                   guid('000214F9-0000-0000-C000-000000000046'), ctypes.byref(link)))
        check(method(link, 20, wintypes.LPCWSTR)(link, str(executable)))
        check(method(link, 9, wintypes.LPCWSTR)(link, str(executable.parent)))
        check(method(link, 7, wintypes.LPCWSTR)(link, 'Tara Windows executor'))
        check(method(link, 0, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            link, guid('0000010B-0000-0000-C000-000000000046'), ctypes.byref(persist)))
        check(method(persist, 6, wintypes.LPCWSTR, wintypes.BOOL)(persist, str(destination), True))
    finally:
        if persist:
            method(persist, 2)(persist)
        if link:
            method(link, 2)(link)
        if initialized >= 0:
            ole.CoUninitialize()


def shortcut_folders():
    shell = ctypes.WinDLL('shell32')
    shell.SHGetFolderPathW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE,
                                     wintypes.DWORD, wintypes.LPWSTR]
    for folder_id in (0x10, 0x02):  # DesktopDirectory and per-user Programs
        buffer = ctypes.create_unicode_buffer(32768)
        result = shell.SHGetFolderPathW(None, folder_id, None, 0, buffer)
        if result != 0 or not buffer.value:
            raise OSError(f'Cannot locate Windows shortcut folder: {folder_id}')
        yield Path(buffer.value)


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
    warnings = []
    try:
        for folder in shortcut_folders():
            try:
                folder.mkdir(parents=True, exist_ok=True)
                create_shortcut(target / 'TaraWorker.exe', folder / 'Tara Worker.lnk')
            except OSError as exc:
                warnings.append(f'{folder}: {exc}')
    except OSError as exc:
        warnings.append(str(exc))
    warning = '\n'.join(warnings)
    # Shortcut creation is optional: copied and verified application is already usable.
    (target.parent / 'install.log').write_text(
        f'Installed: {target}\nShortcut creation: {warning or "OK"}\n', encoding='utf-8')
    return target, warning


def main():
    root = tk.Tk()
    root.title('Установка исполнителя Тары')
    root.geometry('620x300')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Исполнитель Тары', font=('Segoe UI', 14)).pack(anchor='w')
    ttk.Label(frame, text='Установка для текущего пользователя, без прав администратора.\nPython и библиотеки включены. Chromium подготовится при подключении.\nСуществующие настройки и данные сохраняются.', wraplength=520).pack(pady=12)
    status = tk.StringVar(value='Закройте приложение исполнителя перед обновлением.')
    ttk.Label(frame, textvariable=status, wraplength=520).pack()
    events = queue.Queue()
    running = False
    installed = None
    def work():
        try:
            payload = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'installer_payload'
            target, warning = install(payload, lambda text: events.put(('progress', text)))
            if warning:
                events.put(('installed', (target, 'Приложение установлено, но не все ярлыки созданы. Нажмите «Запустить» или «Открыть папку». Причина записана в install.log рядом с каталогом версии.')))
            else:
                events.put(('installed', (target, 'Готово. Запускайте ярлык Tara Worker на рабочем столе.')))
        except Exception as exc:
            events.put(('error', f'Установка не завершена: {type(exc).__name__}. Проверьте доступ к папке и закройте исполнитель.'))
    def start():
        nonlocal running
        running = True
        button.configure(state='disabled')
        status.set('Проверка и установка файлов…')
        threading.Thread(target=work, daemon=False).start()
    def poll():
        nonlocal running, installed
        try:
            while True:
                kind, text = events.get_nowait()
                if kind == 'installed':
                    installed, text = text
                    launch_button.configure(state='normal')
                    folder_button.configure(state='normal')
                status.set(text)
                if kind != 'progress':
                    running = False
                    button.configure(state='normal', text='Закрыть' if kind == 'installed' else 'Повторить', command=root.destroy if kind == 'installed' else start)
        except queue.Empty:
            pass
        root.after(150, poll)
    button = ttk.Button(frame, text='Установить', command=start)
    button.pack(pady=12)
    actions = ttk.Frame(frame)
    actions.pack()
    def launch():
        subprocess.Popen([str(installed / 'TaraWorker.exe')], cwd=installed,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        root.destroy()
    launch_button = ttk.Button(actions, text='Запустить', command=launch, state='disabled')
    launch_button.pack(side='left', padx=8)
    folder_button = ttk.Button(actions, text='Открыть папку', command=lambda: os.startfile(installed), state='disabled')
    folder_button.pack(side='left', padx=8)
    root.protocol('WM_DELETE_WINDOW', lambda: messagebox.showinfo('Установка', 'Дождитесь окончания установки.') if running else root.destroy())
    root.after(150, poll)
    root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        import tempfile
        root = tk.Tk()
        root.withdraw()
        root.update()
        payload = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'installer_payload'
        manifest = json.loads((payload / 'manifest.json').read_text(encoding='utf-8'))
        for name, checksum in manifest.items():
            assert hashlib.sha256((payload / 'app' / name).read_bytes()).hexdigest() == checksum
        with tempfile.TemporaryDirectory() as folder:
            shortcut = Path(folder) / 'Tara Worker.lnk'
            create_shortcut(Path(sys.executable), shortcut)
            assert shortcut.is_file()
        root.destroy()
        Path(sys.argv[2]).write_text(json.dumps({'payload_verified': True, 'windows_shortcut': True, 'tk': True}))
    else:
        main()
