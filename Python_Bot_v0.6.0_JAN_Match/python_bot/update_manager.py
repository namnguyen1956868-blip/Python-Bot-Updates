"""Fixed GitHub Releases updater for Python Bot. Refuses packages without SHA-256 digest."""
import hashlib
import json
import re
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

OWNER = 'namnguyen1956868-blip'
REPOSITORY = 'Python-Bot-Updates'
API = f'https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases/latest'
MAX_ARCHIVE = 30_000_000
ASSET_NAME = re.compile(r'Python_Bot_v(\d+\.\d+\.\d+).*\.zip', re.I)

def version_tuple(v):
    if not re.fullmatch(r'\d+\.\d+\.\d+',str(v)):
        raise ValueError('Phiên bản không hợp lệ')
    return tuple(map(int,v.split('.')))

def secure_github_url(url):
    p=urlparse(url)
    return p.scheme=='https' and p.hostname in ('github.com','objects.githubusercontent.com','release-assets.githubusercontent.com') and not p.username and not p.password

def check_release(current_version):
    req=urllib.request.Request(API,headers={'User-Agent':'PythonBot-Updater/0.4','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=20) as response:
        data=json.loads(response.read(500_000))
    if data.get('draft') or data.get('prerelease'):
        raise ValueError('Release chưa được phát hành chính thức')
    version=data.get('tag_name','').lstrip('v')
    version_tuple(version)
    if version_tuple(version)<=version_tuple(current_version):
        return None
    matches=[]
    for asset in data.get('assets',[]):
        m=ASSET_NAME.fullmatch(asset.get('name',''))
        if m and m.group(1)==version:
            matches.append(asset)
    if len(matches)!=1:
        raise ValueError('Release phải có đúng một file ZIP Python Bot khớp phiên bản tag. Hãy kiểm tra Assets.')
    asset=matches[0]
    digest=asset.get('digest','')
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        raise ValueError('GitHub chưa cung cấp SHA-256 cho asset, không thể xác minh an toàn.')
    url=asset.get('browser_download_url','')
    if not secure_github_url(url) or not url.startswith(f'https://github.com/{OWNER}/{REPOSITORY}/releases/download/'):
        raise ValueError('Nguồn phát hành không hợp lệ')
    return {'version':version,'url':url,'sha256':digest.partition(':')[2]}

def download_release(manifest):
    req=urllib.request.Request(manifest['url'],headers={'User-Agent':'PythonBot-Updater/0.4'})
    with urllib.request.urlopen(req,timeout=60) as response:
        if not secure_github_url(response.geturl()):
            raise ValueError('Nguồn chuyển hướng không tin cậy')
        with tempfile.NamedTemporaryFile(prefix='pythonbot_update_',suffix='.zip',delete=False) as f:
            path=Path(f.name)
            sha=hashlib.sha256()
            total=0
            try:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk: break
                    total+=len(chunk)
                    if total>MAX_ARCHIVE: raise ValueError('Bản cập nhật quá lớn')
                    sha.update(chunk);f.write(chunk)
            except Exception:
                f.close();path.unlink(missing_ok=True);raise
    try:
        if sha.hexdigest().lower()!=manifest['sha256'].lower():
            raise ValueError('SHA-256 không khớp')
        with zipfile.ZipFile(path) as z:
            code=z.read('python_bot/python_bot.py').decode('utf-8')
            if not re.search(r"^VERSION = ['\"]"+re.escape(manifest['version'])+r"['\"]",code,re.M):
                raise ValueError('Phiên bản trong ZIP không trùng với release')
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise
