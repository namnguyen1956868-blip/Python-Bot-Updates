"""Separate installer: waits for Python Bot to exit before replacing files."""
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED = {'python_bot.py', 'update_manager.py', 'apply_update.py',
           'START_PYTHON_BOT.bat', 'START_PYTHON_BOT.vbs', 'START_PYTHON_BOT.pyw', 'README_VI.txt', 'RELEASE_GUIDE.txt', 'discord_listener.py', 'README_DISCORD.txt', 'README_UPDATE.txt'}


def wait_for_exit(pid):
    # Windows: os.kill(pid,0) works to test existence for typical processes.
    for _ in range(120):
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return
        time.sleep(.5)
    raise RuntimeError('Ứng dụng cũ vẫn đang mở; đã hủy cập nhật.')


def install(zip_path, folder, pid):
    wait_for_exit(pid)
    backup = folder / '.pythonbot_update_backup'
    backup.mkdir(exist_ok=True)
    changed = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            members = {PurePosixPath(i.filename).name: i for i in z.infolist()
                       if not i.is_dir() and len(PurePosixPath(i.filename).parts) in (1, 2)}
            # Require all files to exist inside exactly one python_bot/ directory.
            for item in z.infolist():
                p = PurePosixPath(item.filename)
                if item.is_dir():
                    continue
                if len(p.parts) != 2 or p.parts[0] != 'python_bot' or p.name not in ALLOWED:
                    raise ValueError('ZIP chứa đường dẫn hoặc file không được phép: ' + item.filename)
                if item.file_size > 5_000_000:
                    raise ValueError('File trong ZIP quá lớn.')
            if not {'python_bot.py', 'update_manager.py', 'apply_update.py'} <= members.keys():
                raise ValueError('Bộ cập nhật thiếu file cần thiết.')
            for name in ALLOWED & members.keys():
                target = folder / name
                saved = backup / name
                if target.exists():
                    shutil.copy2(target, saved)
                else:
                    saved.unlink(missing_ok=True)
                changed.append((target, saved, target.exists()))
                temp = folder / (name + '.new')
                try:
                    with z.open(members[name]) as src, temp.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(temp, target)
                finally:
                    temp.unlink(missing_ok=True)
    except Exception:
        for target, saved, existed in reversed(changed):
            if existed and saved.exists():
                shutil.copy2(saved, target)
            elif not existed:
                target.unlink(missing_ok=True)
        raise
    finally:
        zip_path.unlink(missing_ok=True)
    shutil.rmtree(backup, ignore_errors=True)
    os.startfile(str(folder / 'START_PYTHON_BOT.vbs')) if os.name == 'nt' else None


if __name__ == '__main__':
    try:
        install(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
    except Exception as exc:
        # Keep an error report for troubleshooting; never put secrets here.
        (Path(sys.argv[2]) / 'update_error.txt').write_text(str(exc), encoding='utf-8')
