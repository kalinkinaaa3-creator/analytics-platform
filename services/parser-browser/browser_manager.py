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


def resolve_profile(environment, selected=''):
    if not selected:
        return data_dir() / environment / 'profile', None
    path = Path(os.path.expandvars(selected.strip())).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('Выберите существующую папку профиля Chromium по полному пути.')
    path = path.resolve()
    if (path / 'Local State').is_file():
        return path, None
    if (path.parent / 'Local State').is_file() and (path / 'Preferences').is_file():
        return path.parent, path.name
    raise ValueError('В выбранной папке не найден профиль Chromium. Выберите каталог с Local State или папку профиля из chrome://version.')


def start_browser(executable, environment, product, report, stop, selected_profile=''):
    profile, profile_name = resolve_profile(environment, selected_profile)
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
        except (ValueError, IndexError, OSError, requests.RequestException):
            active.unlink(missing_ok=True)
    report('Открывается отдельный Chromium. Дождитесь карточки товара в его окне.')
    args = [str(executable), f'--user-data-dir={profile}',
                      '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
                      '--no-first-run', '--no-default-browser-check']
    if profile_name:
        args.append(f'--profile-directory={profile_name}')
    args.append(product)
    child = subprocess.Popen(args,
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
        if child.poll() is not None:
            raise RuntimeError('Chromium не открыл подключение. Закройте все его окна с выбранным профилем (и старый worker.py), затем повторите. Профиль не удалён.')
        time.sleep(.25)
    raise RuntimeError('Chromium не открыл порт подключения. Закройте его служебное окно и повторите.')


def _close_process_windows(pid):
    """Request a normal window close for this process only; never kill Chrome globally."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    @callback_type
    def close(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE, allowing profile flush.
        return True
    user32.EnumWindows(close, 0)


def _plain_profile_visit(executable, profile, profile_name, product, report, stop):
    args = [str(executable), f'--user-data-dir={profile}']
    if profile_name:
        args.append(f'--profile-directory={profile_name}')
    args.append(product)
    # Same arguments as the displayed PowerShell command; no debugging switches.
    child = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    report('Recovery: ordinary Chromium opened without debugging. Waiting 30 seconds; page status is not observable in this phase.')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not stop.is_set():
        if child.poll() is not None:
            raise RuntimeError('Ordinary Chromium exited or handed off to another process; recovery stopped.')
        time.sleep(.25)
    if stop.is_set():
        return False  # Leave the browser open on user cancellation.
    _close_process_windows(child.pid)
    try:
        child.wait(timeout=20)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Chromium did not close normally; close its service window before reconnecting.')
    return True


async def select_service_tab(browser, product, report, navigate=True):
    """Keep the requested Tara tab; never close tabs belonging to other sites."""
    from worker import allowed
    if not allowed(product):
        raise ValueError('Invalid service card URL')
    pages = [(c, p) for c in browser.contexts for p in c.pages if allowed(p.url)]
    selected = next(((c, p) for c, p in pages if p.url == product), None)
    if selected is None:
        if pages:
            selected = pages[0]
        else:
            context = browser.contexts[0]
            selected = context, await context.new_page()
        if navigate or not pages:
            await selected[1].goto(product, wait_until='domcontentloaded', timeout=45000)
    # Re-enumerate: Chromium may have restored additional tabs during navigation.
    closed = 0
    for context in browser.contexts:
        for page in list(context.pages):
            if page is not selected[1] and allowed(page.url):
                await page.close()
                closed += 1
    if closed:
        report(f'Service tab: closed {closed} extra Tara tab(s); other sites left unchanged.')
    return selected


async def recover_service_browser(pw, browser, executable, environment, product, report, stop, selected_profile=''):
    import asyncio
    from worker import allowed, card
    # Refuse to close a browser containing personal/non-service tabs.
    pages = [p for context in browser.contexts for p in context.pages]
    if not pages or any(not allowed(p.url) for p in pages):
        report('Recovery requires exactly one Tara service tab; browser left open.')
        return None
    await select_service_tab(browser, product, report)
    profile, profile_name = resolve_profile(environment, selected_profile)
    report('Recovery: closing service Chromium before ordinary launch.')
    session = await browser.new_browser_cdp_session()
    try:
        await session.send('Browser.close')
    except Exception:
        if browser.is_connected():
            raise
    for _ in range(80):
        if not browser.is_connected():
            break
        await asyncio.sleep(.25)
    else:
        raise RuntimeError('Service Chromium is still connected; recovery stopped.')
    # Allow the browser to flush its profile and release the singleton lock.
    await asyncio.sleep(2)
    if stop.is_set():
        return None
    if not await asyncio.to_thread(_plain_profile_visit, executable, profile, profile_name, product, report, stop):
        return None
    if stop.is_set():
        return None
    # A closed browser's port file must not select a stale endpoint.
    (profile / 'DevToolsActivePort').unlink(missing_ok=True)
    report('Recovery: restarting Chromium with debugging and checking the service card.')
    endpoint = await asyncio.to_thread(start_browser, executable, environment, product, report, stop, selected_profile)
    replacement = await pw.chromium.connect_over_cdp(endpoint, timeout=15000)
    context, page = await select_service_tab(replacement, product, report)
    for _ in range(30):
        if stop.is_set():
            return None
        context, page = await select_service_tab(replacement, product, report, navigate=False)
        try:
            if card(await page.content()):
                report('Recovery: service card found. Reading cookies and retrying blocked tasks.')
                return replacement, context, page
        except Exception:
            pass  # Document may be navigating.
        await asyncio.sleep(1)
    report('Recovery did not restore the service card. Browser left open; executor will stop.')
    return None
