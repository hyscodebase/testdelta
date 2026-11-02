"""Check a static launch site without running scripts or fetching third parties."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / 'site'


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.ids = set()
        self.title = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'title':
            self.title = True
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.references.append(attrs[key])


def main():
    assert (ROOT / 'index.html').is_file(), 'Missing launch homepage'
    pages = {}
    for path in ROOT.rglob('*.html'):
        page = Page()
        page.feed(path.read_text(encoding='utf-8'))
        assert page.title, f'Missing page title: {path.relative_to(ROOT)}'
        pages[path.resolve()] = page
    checked = 0
    for path, page in pages.items():
        for reference in page.references:
            url = urlsplit(reference)
            if url.scheme or url.netloc:
                assert url.scheme in {'https', 'mailto', 'data'}, reference
                continue
            local = unquote(url.path)
            if local.startswith('/testdelta/'):
                target = ROOT / local.removeprefix('/testdelta/')
            elif local.startswith('/'):
                raise AssertionError(f'Root URL misses project base: {reference}')
            else:
                target = path.parent / local if local else path
            target = target.resolve()
            assert target.is_relative_to(ROOT.resolve()), reference
            if target.is_dir():
                target /= 'index.html'
            assert target.is_file(), f'Missing local asset: {reference}'
            if url.fragment and target in pages:
                assert unquote(url.fragment) in pages[target].ids, reference
            checked += 1
    print(f'Checked {len(pages)} HTML pages and {checked} local asset/anchor references')


if __name__ == '__main__':
    main()
