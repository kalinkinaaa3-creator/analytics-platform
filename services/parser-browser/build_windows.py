"""Build on Windows with the build venv: python build_windows.py."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    if os.name != 'nt':
        raise SystemExit('Build on Windows')
    os.chdir(ROOT)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--console', '--hide-console', 'hide-early',
                    '--onedir', '--name', 'TaraWorker', '--collect-all', 'playwright', 'launcher.py'], check=True)
    payload = ROOT / 'build' / 'installer_payload'
    app = payload / 'app'
    # All paths are fixed descendants of this build directory.
    if payload.exists():
        if not payload.resolve().is_relative_to((ROOT / 'build').resolve()):
            raise RuntimeError('Invalid build path')
        shutil.rmtree(payload)
    shutil.copytree(ROOT / 'dist' / 'TaraWorker', app)
    manifest = {p.relative_to(app).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(app.rglob('*')) if p.is_file()}
    (payload / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--console', '--hide-console', 'hide-early',
                    '--onefile', '--name', 'TaraWorkerSetup', '--add-data',
                    str(payload) + ';installer_payload', 'setup_windows.py'], check=True)
    print(ROOT / 'dist' / 'TaraWorkerSetup.exe')


if __name__ == '__main__':
    main()
