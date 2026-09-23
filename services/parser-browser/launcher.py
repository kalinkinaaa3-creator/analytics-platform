"""Interactive Windows entry point. No automatic startup or background service."""
import asyncio
import contextlib
import msvcrt
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import uuid
import sys

from browser_manager import PRODUCT, ensure_browser, start_browser, resolve_profile
from settings_store import data_dir, environment_id, get_key, load, normalize_api, save
import worker


class Output:
    def __init__(self, messages):
        self.messages = messages

    def write(self, text):
        if text.strip():
            self.messages.put(('log', text.strip()))

    def flush(self):
        pass


async def run_executor(endpoint, product, stop, report):
    # User can complete site checks in the visible browser before any jobs are claimed.
    async with worker.async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(endpoint, timeout=15000)
        pages = [p for c in browser.contexts for p in c.pages if worker.allowed(p.url)]
        if not pages:
            page = await browser.contexts[0].new_page()
            await page.goto(product, wait_until='domcontentloaded', timeout=45000)
        elif len(pages) == 1 and pages[0].url != product:
            await pages[0].goto(product, wait_until='domcontentloaded', timeout=45000)
        report('Проверка служебной вкладки. Если сайт требует действия — выполните его в Chromium.')
        for _ in range(240):
            if stop.is_set():
                return
            pages = [p for c in browser.contexts for p in c.pages if worker.allowed(p.url)]
            if len(pages) == 1:
                try:
                    if worker.card(await pages[0].content()):
                        break
                except Exception:
                    pass  # Navigation can replace the document during the check.
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Карточка не открылась. Оставьте одну вкладку Тары и повторите подключение.')
    await worker.main(stop)


class App:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.thread = None
        self.closing = False
        root.title('Исполнитель Тары')
        root.geometry('780x720')
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Подтвердите адрес API перед каждым подключением:').pack(anchor='w')
        try:
            config = load()
        except Exception:
            config = {}
            messagebox.showerror('Настройки', 'Не удалось прочитать настройки. Проверьте settings.json в каталоге данных.')
        self.api = tk.StringVar(value=config.get('last_api', 'http://127.0.0.1:18000/api'))
        self.address = ttk.Entry(frame, textvariable=self.api)
        self.address.pack(fill='x', pady=8)
        ttk.Label(frame, text='Служебная карточка Тары (ссылка сохраняется для выбранного API):').pack(anchor='w')
        self.product = tk.StringVar(value=config.get('products', {}).get(self.api.get(), PRODUCT))
        self.product_entry = ttk.Entry(frame, textvariable=self.product)
        self.product_entry.pack(fill='x', pady=8)
        self.address.bind('<FocusOut>', self.load_product)
        ttk.Label(frame, text='Chromium: можно выбрать установленный chrome.exe; пустое поле — автоматическая подготовка.').pack(anchor='w')
        browser_row = ttk.Frame(frame)
        browser_row.pack(fill='x', pady=8)
        self.browser_path = tk.StringVar(value=config.get('browser', ''))
        self.browser_entry = ttk.Entry(browser_row, textvariable=self.browser_path)
        self.browser_entry.pack(side='left', fill='x', expand=True)
        self.browser_button = ttk.Button(browser_row, text='Выбрать…', command=self.choose_browser)
        self.browser_button.pack(side='left', padx=8)
        ttk.Label(frame, text='Профиль Chromium: пусто — отдельный; для прежней сессии выберите существующий.').pack(anchor='w')
        profile_row = ttk.Frame(frame)
        profile_row.pack(fill='x', pady=8)
        self.profile_path = tk.StringVar(value=config.get('profiles', {}).get(self.api.get(), ''))
        self.profile_entry = ttk.Entry(profile_row, textvariable=self.profile_path)
        self.profile_entry.pack(side='left', fill='x', expand=True)
        self.profile_button = ttk.Button(profile_row, text='Выбрать…', command=self.choose_profile)
        self.profile_button.pack(side='left', padx=8)
        ttk.Label(frame, text='Перед использованием прежнего профиля закройте работающий с ним Chromium и старый воркер.').pack(anchor='w')
        ttk.Label(frame, text='Для рабочего сервера включите VPN. Запуск обхода — на дашборде или в Airflow.').pack(anchor='w')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=12)
        self.start_button = ttk.Button(buttons, text='Подключить исполнитель', command=self.start)
        self.start_button.pack(side='left')
        self.key_button = ttk.Button(buttons, text='Изменить ключ', command=self.change_key)
        self.key_button.pack(side='left', padx=8)
        self.stop_button = ttk.Button(buttons, text='Остановить', command=self.request_stop, state='disabled')
        self.stop_button.pack(side='left')
        self.state = tk.StringVar(value='Не подключён')
        ttk.Label(frame, textvariable=self.state, wraplength=740).pack(anchor='w', pady=6)
        self.log = tk.Text(frame, height=14, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(150, self.poll)

    def ask_key(self, api):
        value = simpledialog.askstring('Ключ исполнителя', f'TARA_WORKER_KEY для\n{api}', show='*', parent=self.root)
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError('Ключ не должен быть пустым')
        save(api, value)
        return value

    def choose_browser(self):
        path = filedialog.askopenfilename(title='Выберите chrome.exe Chromium', filetypes=[('Chromium', 'chrome.exe')])
        if path:
            self.browser_path.set(path)

    def choose_profile(self):
        path = filedialog.askdirectory(title='Папка профиля Chromium (с Local State или Preferences)')
        if path:
            self.profile_path.set(path)

    def load_product(self, event=None):
        try:
            api = normalize_api(self.api.get())
            if api != getattr(self, '_product_api', None):
                self.product.set(load().get('products', {}).get(api, PRODUCT))
                self.profile_path.set(load().get('profiles', {}).get(api, ''))
                self._product_api = api
        except (ValueError, OSError):
            pass

    def change_key(self):
        try:
            self.ask_key(normalize_api(self.api.get()))
        except Exception as exc:
            messagebox.showerror('Настройки', str(exc))

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        try:
            api = normalize_api(self.api.get())
            product = self.product.get().strip()
            if not worker.allowed(product):
                raise ValueError('Укажите HTTPS-ссылку на карточку tara.ru или его регионального поддомена.')
            key = get_key(load(), api) or self.ask_key(api)
            if key is None:
                return
            browser_path = self.browser_path.get().strip()
            profile_path = self.profile_path.get().strip()
            resolve_profile(environment_id(api), profile_path)
            save(api, key, product, browser_path, profile_path)
        except Exception as exc:
            messagebox.showerror('Настройки', str(exc))
            return
        self.stop.clear()
        self.start_button.configure(state='disabled')
        self.key_button.configure(state='disabled')
        self.address.configure(state='disabled')
        self.product_entry.configure(state='disabled')
        self.browser_entry.configure(state='disabled')
        self.browser_button.configure(state='disabled')
        self.profile_entry.configure(state='disabled')
        self.profile_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.state.set('Подготовка подключения…')
        self.thread = threading.Thread(target=self.execute, args=(api, key, product, browser_path, profile_path), daemon=False)
        self.thread.start()

    def execute(self, api, key, product, browser_path, profile_path):
        report = lambda text: self.messages.put(('log', text))
        try:
            environment = environment_id(api)
            executable = ensure_browser(report, self.stop, browser_path)
            if self.stop.is_set():
                return
            endpoint = start_browser(executable, environment, product, report, self.stop, profile_path)
            worker.BASE, worker.KEY, worker.CDP = api, key, endpoint
            worker.OWNER = uuid.uuid4().hex
            worker.OUTBOX = data_dir() / environment / 'outbox'
            with contextlib.redirect_stdout(Output(self.messages)):
                asyncio.run(run_executor(endpoint, product, self.stop, report))
        except Exception as exc:
            # Never display headers, stored settings or a supplied secret.
            detail = str(exc).replace(key, '[скрыто]')
            report(f'Не удалось продолжить: {type(exc).__name__}: {detail}')
        finally:
            worker.KEY = ''
            self.messages.put(('done', 'Исполнитель остановлен. Chromium оставлен открытым.'))

    def request_stop(self):
        self.stop.set()
        self.stop_button.configure(state='disabled')
        self.state.set('Остановка после текущей группы запросов. Дождитесь сохранения результатов…')

    def close(self):
        if self.thread and self.thread.is_alive():
            if messagebox.askyesno('Завершить работу', 'Остановить исполнитель после текущей группы запросов и закрыть приложение?'):
                self.closing = True
                self.request_stop()
        else:
            self.root.destroy()

    def poll(self):
        try:
            while True:
                kind, text = self.messages.get_nowait()
                self.log.configure(state='normal')
                self.log.insert('end', text + '\n')
                if int(self.log.index('end-1c').split('.')[0]) > 1000:
                    self.log.delete('1.0', '200.0')
                self.log.see('end')
                self.log.configure(state='disabled')
                if not self.stop.is_set():
                    self.state.set(text[:240])
                if kind == 'done':
                    self.state.set(text)
                    self.start_button.configure(state='normal')
                    self.key_button.configure(state='normal')
                    self.address.configure(state='normal')
                    self.product_entry.configure(state='normal')
                    self.browser_entry.configure(state='normal')
                    self.browser_button.configure(state='normal')
                    self.profile_entry.configure(state='normal')
                    self.profile_button.configure(state='normal')
                    self.stop_button.configure(state='disabled')
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(150, self.poll)


def main():
    root = tk.Tk()
    data_dir().mkdir(parents=True, exist_ok=True)
    lock = (data_dir() / 'launcher.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        root.withdraw()
        messagebox.showinfo('Исполнитель Тары', 'Приложение уже запущено. Используйте его открытое окно.')
        root.destroy()
        lock.close()
        return
    try:
        App(root)
        root.mainloop()
    finally:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        # Offline packaging check: Tk, DPAPI and the bundled Playwright driver.
        import json
        from pathlib import Path
        from settings_store import crypt
        from playwright._impl._driver import compute_driver_executable
        root = tk.Tk()
        root.withdraw()
        root.update()
        node, cli = compute_driver_executable()
        assert Path(node).is_file() and Path(cli).is_file()
        assert crypt(crypt(b'packaging-test'), decrypt=True) == b'packaging-test'
        root.destroy()
        Path(sys.argv[2]).write_text(json.dumps({'tk':True, 'dpapi':True, 'playwright_driver':True}))
    else:
        main()
