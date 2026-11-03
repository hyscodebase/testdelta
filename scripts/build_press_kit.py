"""Build a deterministic public press kit from reviewed repository assets."""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    files = {
        'copy/launch-kit.md': (ROOT / 'docs/launch-kit.md').read_bytes(),
        'LICENSE': (ROOT / 'LICENSE').read_bytes(),
    }
    for name in ('index.html', 'report.html', 'styles.css', 'script.js', 'recorded-case.json'):
        payload = (ROOT / 'site' / name).read_bytes()
        if name == 'index.html':
            payload = payload.replace(b'href="downloads/testdelta-press-kit.zip"', b'href="https://hyscodebase.github.io/testdelta/downloads/testdelta-press-kit.zip"')
        files['demo/' + name] = payload
    for path in sorted((ROOT / 'site/assets').iterdir()):
        if path.suffix in {'.svg', '.png'}:
            files['demo/assets/' + path.name] = path.read_bytes()
            files['branding/' + path.name] = path.read_bytes()
    files['README.ko.md'] = (
        '# TestDelta 홍보 키트\n\n'
        '공개 소개: https://hyscodebase.github.io/testdelta/\n'
        'Marketplace: https://github.com/marketplace/actions/testdelta-test-quality\n'
        '공개 버전: v0.1.0-alpha.4 (초기 알파)\n'
        '저장소: https://github.com/hyscodebase/testdelta\n'
        'Action 안내: https://github.com/hyscodebase/testdelta/blob/main/docs/action.md\n\n'
        'copy/launch-kit.md에 한영 소개·LinkedIn·X·커뮤니티·Show HN 초안이 있습니다.\n'
        'branding/social-card.png는 1200×630 공유 이미지이며 원본 SVG도 포함합니다.\n'
        'demo/index.html은 오프라인에서 열 수 있는 정적 소개/사례 페이지입니다. '
        '이 페이지가 Python 테스트를 실행하는 것은 아닙니다.\n\n'
        'Marketplace 등록과 설치 버전은 공개 페이지에서 확인했습니다. '
        '이 키트는 외부 SNS/커뮤니티에 게시물을 자동으로 보내지 않습니다.\n'
        '자료와 이미지의 라이선스는 LICENSE를 확인하세요. 개인 DB·raw 결과·환경 파일은 포함하지 않습니다.\n'
    ).encode('utf-8')
    files['SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(value).hexdigest()}  {name}\n'
        for name, value in sorted(files.items())
    ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, value in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, value)
    destination = ROOT / 'site/downloads/testdelta-press-kit.zip'
    destination.parent.mkdir(exist_ok=True)
    destination.write_bytes(buffer.getvalue())
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(files)
    print(f'Created public press kit: {len(files)} files, {destination.stat().st_size} bytes')


if __name__ == '__main__':
    main()
