"""OAuth notices are inert HTML; the edge has a separate real HTTP smoke."""
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('name',['index.html','privacy.html'])
def test_public_backup_information_has_no_active_or_external_assets(name):
    class Page(HTMLParser):
        def __init__(self):
            super().__init__();self.tags=[];self.attributes=[]
        def handle_starttag(self,tag,attrs):
            self.tags.append(tag);self.attributes.append((tag,dict(attrs)))
    text=(ROOT/'deploy/backup-info'/name).read_text()
    page=Page();page.feed(text)
    assert 'NextPhase Backups' in text and len(text.encode())<20000
    assert not {'script','iframe','object','embed','form','input','img','link'} & set(page.tags)
    assert page.tags.count('h1')==1
    assert ('html',{'lang':'en'}) in page.attributes
    assert any(tag=='meta' and attrs.get('name')=='viewport' for tag,attrs in page.attributes)
    for tag,attrs in page.attributes:
        assert not any(key.startswith('on') for key in attrs)
        assert not {'src','srcset'} & set(attrs)
        if tag=='a':assert attrs['href'].startswith(('/backup-','mailto:'))
