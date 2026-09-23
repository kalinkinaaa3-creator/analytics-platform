"""Own browser profile and loopback CDP endpoint; no changes to personal browsers."""
import os
from pathlib import Path
import subprocess
import time

import requests
from playwright.sync_api import sync_playwright
from playwright._impl._driver import compute_driver_executable, get_driver_env

from settings_store import data_dir

PRODUCT = 'https://moskva.tara.ru/catalog/nalivnaya_tara/plastikovaya_yemkost_200_litrov/?oid=241441'


def ensure_browser(report, stop, selected=''):
    if selected:
        executable = Path(selected)
        if not executable.is_file() or executable.name.lower() != 'chrome.exe':
            raise ValueError('Выберите существующий chrome.exe установленного Chromium')
        return executable
    for root in (os.environ.get('LOCALAPPDATA'), os.environ.get('PROGRAMFILES'), os.environ.get('PROGRAMFILES(X86)')):
        if root:
            executable = Path(root) / 'Chromium' / 'Application' / 'chrome.exe'
            if executable.is_file():
                return executable
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(data_dir() / 'browsers')
    with sync_playwright() as pw:
        executable = Path(pw.chromium.executable_path)
    if executable.is_file():
        return executable
    report('Первая подготовка: скачивается Chromium. Это может занять несколько минут.')
    node, cli = compute_driver_executable()
    with subprocess.Popen([node, cli, 'install', 'chromium', '--no-shell'],
                          env=get_driver_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NO_WINDOW) as child:
        # Consume pipe continuously; installer output is not allowed to fill the pipe.
        import threading
        def drain():
            for line in child.stdout:
                pass
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + 900
        while child.poll() is None:
            if stop.is_set() or time.monotonic() > deadline:
                # Node is the downloader; no browser is running at this stage.
                child.terminate()
                child.wait()
                raise RuntimeError('Подготовка Chromium отменена или превышено время ожидания')
            time.sleep(.3)
        if child.returncode or not executable.is_file():
            raise RuntimeError('Не удалось скачать Chromium. Проверьте интернет и повторите запуск.')
    return executable


def start_browser(executable, environment, product, report, stop):
    profile = data_dir() / environment / 'profile'
    profile.mkdir(parents=True, exist_ok=True)
    active = profile / 'DevToolsActivePort'
    if active.exists():
        try:
            port = int(active.read_text().splitlines()[0])
            endpoint = f'http://127.0.0.1:{port}'
            with requests.Session() as client:
                client.trust_env = False
                response = client.get(endpoint + '/json/version', timeout=2)
                response.raise_for_status()
            return endpoint
        except (ValueError, OSError, requests.RequestException):
            active.unlink(missing_ok=True)
    report('Открывается отдельный Chromium. Дождитесь карточки товара в его окне.')
    subprocess.Popen([str(executable), f'--user-data-dir={profile}',
                      '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
                      '--no-first-run', '--no-default-browser-check', product],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(120):
        if stop.is_set():
            raise RuntimeError('Запуск отменён')
        if active.exists():
            try:
                port = int(active.read_text().splitlines()[0])
                return f'http://127.0.0.1:{port}'
            except (ValueError, IndexError, OSError):
                pass
        time.sleep(.25)
    raise RuntimeError('Chromium не открыл порт подключения. Закройте его служебное окно и повторите.')
