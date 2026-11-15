"""Consent-gated public Commons search and bounded downloads; no arbitrary URLs.

Only CC0/public-domain metadata is accepted in this first prototype. Search is
not a factual-verification service. Metadata text remains untrusted source data.
No private transcript, query text, native logs or credentials are logged.
"""
import hashlib,json,os,re,time
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qsl, urlunsplit
import httpx
from .documentary_plan import AssetReceipt,DocumentaryFailure,commons_url

API='https://commons.wikimedia.org/w/api.php'
USER_AGENT='NextPhaseShorts/0.1 (https://github.com/Ngum12/NextPhase-Shorts; development)'
MAX_METADATA=262144


class _Plain(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,value):self.parts.append(value)


def plain(value,limit):
    if not isinstance(value,str):return ''
    parser=_Plain();parser.feed(value[:10000])
    return re.sub(r'\s+',' ',''.join(parser.parts)).strip()[:limit]


class CommonsResearch:
    """One explicit public-topic research session: <=3 searches, <=3 assets/24MiB.

    Future app admission must reserve this budget and disclose external search.
    This class is currently reachable only through tests/operator demonstration.
    """
    def __init__(self,*,consented,client=None):
        if consented is not True:raise DocumentaryFailure('CONSENT_REQUIRED')
        self.client=client or httpx.Client(timeout=httpx.Timeout(10,connect=5),follow_redirects=False)
        self.issued={};self.owned=client is None;self.requests=0;self.downloads=0;self.bytes=0;self.began=time.monotonic()

    def close(self):
        if self.owned:self.client.close()

    def _get(self,url,*,maximum,params=None,download=False):
        if time.monotonic()-self.began>60:raise DocumentaryFailure('DEADLINE_EXCEEDED')
        chunks=[];size=0
        try:
            with self.client.stream('POST' if params else 'GET',url,data=params,headers={'User-Agent':USER_AGENT,'Accept-Encoding':'identity'},
                    timeout=httpx.Timeout(10,connect=5),follow_redirects=False) as response:
                if response.status_code!=200:raise DocumentaryFailure('RESEARCH_UNAVAILABLE')
                if response.headers.get('content-encoding','identity').lower()!='identity':raise DocumentaryFailure('DOWNLOAD_REJECTED')
                length=response.headers.get('content-length')
                if length is not None and (not length.isdigit() or int(length)>maximum):raise DocumentaryFailure('DOWNLOAD_REJECTED')
                for chunk in response.iter_raw(chunk_size=65536):
                    size+=len(chunk)
                    if download:
                        self.bytes+=len(chunk)
                        if self.bytes>25165824:raise DocumentaryFailure('DOWNLOAD_REJECTED')
                    if size>maximum or time.monotonic()-self.began>60:raise DocumentaryFailure('DOWNLOAD_REJECTED')
                    chunks.append(chunk)
            return b''.join(chunks)
        except (httpx.HTTPError,httpx.InvalidURL,UnicodeError):raise DocumentaryFailure('RESEARCH_UNAVAILABLE') from None

    def search(self,query,*,kind='image'):
        if (not isinstance(query,str) or not 1<=len(query)<=80 or not query.strip() or
                any(ord(c)<32 or ord(c)==127 for c in query) or kind not in ('image','video') or self.requests>=3):
            raise DocumentaryFailure('PLAN_INVALID')
        self.requests+=1
        params={'action':'query','format':'json','generator':'search','gsrnamespace':6,'gsrlimit':8,
            'gsrsearch':query+(' filetype:bitmap' if kind=='image' else ' filetype:video'),
            'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':1920,'iiurlheight':1920,
            'iiextmetadatafilter':'Artist|Credit|LicenseShortName|License|UsageTerms'}
        try:data=json.loads(self._get(API,maximum=MAX_METADATA,params=params))
        except (ValueError,TypeError):raise DocumentaryFailure('RESEARCH_UNAVAILABLE') from None
        if not isinstance(data,dict) or 'error' in data or not isinstance(data.get('query',{}),dict):raise DocumentaryFailure('RESEARCH_UNAVAILABLE')
        pages=data.get('query',{}).get('pages',{})
        if not isinstance(pages,dict) or len(pages)>8:raise DocumentaryFailure('RESEARCH_UNAVAILABLE')
        result=[]
        for page in sorted(pages.values(),key=lambda p:p.get('index',999) if isinstance(p,dict) and type(p.get('index',999)) is int else 999):
            try:
                info=page['imageinfo'][0];meta=info['extmetadata']
                def field(name):return plain(meta.get(name,{}).get('value',''),500)
                name=field('LicenseShortName').lower();license_code=field('License').lower()
                if name in ('cc0','cc0 1.0','cc0 1.0 universal') or license_code=='cc-zero':license='CC0-1.0'
                elif name=='public domain' and (license_code in ('pd','public-domain') or field('UsageTerms').lower()=='public domain'):
                    license='public-domain'
                else:continue
                if kind=='video' and (type(info.get('size')) is not int or not 0<info['size']<=16777216):continue
                if kind=='image' and (type(info.get('size')) is not int or not 0<info['size']<=8388608):continue
                if kind=='image' and (type(info.get('width')) is not int or type(info.get('height')) is not int or
                    not 16<=info['width']<=4096 or not 16<=info['height']<=4096 or info['width']*info['height']>8294400):continue
                mime=info['mime'];url=info['url']
                # Commons adds analytics to original URLs. Drop only its exact
                # documented tracking tuple; all other query strings fail closed.
                parsed=urlsplit(url)
                if parsed.query and dict(parse_qsl(parsed.query,keep_blank_values=True))=={
                    'utm_source':'commons.wikimedia.org','utm_campaign':'imageinfo','utm_content':'original'}:
                    url=urlunsplit(parsed._replace(query=''))
                if (kind=='image' and mime!='image/jpeg') or (kind=='video' and mime!='video/webm'):continue
                if not commons_url(url,'upload.wikimedia.org','/wikipedia/commons/'):continue
                source=info['descriptionurl']
                if not commons_url(source,'commons.wikimedia.org','/wiki/File:'):continue
                result.append({'kind':kind,'url':url,'source_url':source,'title':plain(page['title'],300),
                    'creator':field('Artist') or field('Credit') or 'Creator not supplied','license':license})
            except (ValueError,KeyError,TypeError,IndexError,AttributeError):continue
        for candidate in result:self.issued[candidate['url']]=json.dumps(candidate,sort_keys=True)
        return result

    def search_context(self,query):
        """Return attributed source excerpts; retrieval is not fact verification."""
        if (not isinstance(query,str) or not 1<=len(query)<=80 or not query.strip() or
                any(ord(c)<32 or ord(c)==127 for c in query) or self.requests>=3):
            raise DocumentaryFailure('PLAN_INVALID')
        self.requests+=1
        try:
            data=json.loads(self._get('https://en.wikipedia.org/w/api.php',maximum=MAX_METADATA,
                params={'action':'query','format':'json','list':'search','srsearch':query,'srlimit':3}))
            entries=data['query']['search']
            if not isinstance(entries,list) or len(entries)>3:raise ValueError()
            return [{'title':plain(item['title'],300),'excerpt':plain(item['snippet'],1000),
                'source_url':'https://en.wikipedia.org/wiki/'+quote(item['title'].replace(' ','_'),safe='()_-')}
                for item in entries if isinstance(item,dict) and isinstance(item.get('title'),str)]
        except DocumentaryFailure:raise
        except (ValueError,KeyError,TypeError):raise DocumentaryFailure('RESEARCH_UNAVAILABLE') from None

    def download(self,candidate,directory):
        if self.downloads>=3:raise DocumentaryFailure('DOWNLOAD_REJECTED')
        try:
            url=candidate['url'];kind=candidate['kind']
            if self.issued.get(url)!=json.dumps(candidate,sort_keys=True):raise DocumentaryFailure('RIGHTS_UNCONFIRMED')
            if kind not in ('image','video') or not commons_url(url,'upload.wikimedia.org','/wikipedia/commons/'):
                raise DocumentaryFailure('DOWNLOAD_REJECTED')
            maximum=min(8388608 if kind=='image' else 16777216,25165824-self.bytes)
            if maximum<=0:raise DocumentaryFailure('DOWNLOAD_REJECTED')
            self.downloads+=1
            data=self._get(url,maximum=maximum,download=True)
            if (kind=='image' and not data.startswith(b'\xff\xd8\xff')) or (kind=='video' and not data.startswith(b'\x1aE\xdf\xa3')):
                raise DocumentaryFailure('ASSET_UNSUPPORTED')
            digest=hashlib.sha256(data).hexdigest()
            receipt=AssetReceipt(asset_id=digest,kind=kind,origin='commons',creator=candidate['creator'],title=candidate['title'],
                license=candidate['license'],source_url=candidate['source_url'],download_url=url,
                retrieved_at=datetime.now(timezone.utc).isoformat(),bytes=len(data))
            directory=Path(directory)
            if any(p.is_symlink() for p in (directory,*directory.parents)):raise DocumentaryFailure('DOWNLOAD_REJECTED')
            directory.mkdir(mode=0o700,parents=True,exist_ok=True)
            path=directory/(digest+('.jpg' if kind=='image' else '.webm'))
            with path.open('xb') as output:os.chmod(path,0o600);output.write(data)
            return receipt,path
        except DocumentaryFailure:raise
        except (ValueError,KeyError,TypeError,OSError):raise DocumentaryFailure('DOWNLOAD_REJECTED') from None
