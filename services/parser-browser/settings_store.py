"""Per-user configuration; secrets are encrypted with Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def data_dir():
    return Path(os.environ['LOCALAPPDATA']) / 'AnalyticsPlatform' / 'TaraWorkerData'


def normalize_api(value):
    value = value.strip().rstrip('/')
    u = urlsplit(value)
    if (u.username or u.password or u.query or u.fragment or not u.hostname
            or u.path != '/api' or u.port == 0
            or not (u.scheme == 'https' or u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1'))):
        raise ValueError('Укажите HTTPS-адрес с окончанием /api. HTTP разрешён только для localhost и 127.0.0.1.')
    return u._replace(netloc=u.netloc.lower()).geturl()


def environment_id(api):
    return hashlib.sha256(normalize_api(api).encode()).hexdigest()[:24]


class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Защищённое хранилище доступно только в Windows')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    function = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    function.restype = wintypes.BOOL
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


def load():
    path = data_dir() / 'settings.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'keys': {}}


def get_key(config, api):
    value = config.get('keys', {}).get(normalize_api(api))
    return crypt(base64.b64decode(value), decrypt=True).decode() if value else ''


def save(api, key, product=None, browser=None):
    api = normalize_api(api)
    config = load()
    config.setdefault('keys', {})[api] = base64.b64encode(crypt(key.encode())).decode()
    config['last_api'] = api
    if product is not None:
        config.setdefault('products', {})[api] = product
    if browser is not None:
        config['browser'] = browser
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / 'settings.tmp'
    temporary.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    temporary.replace(root / 'settings.json')
