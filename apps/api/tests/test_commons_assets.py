"""No real network or private data: fixed origins, source rights and byte budgets."""
import json
import httpx
import pytest
from app.commons_assets import CommonsResearch
from app.documentary_plan import DocumentaryFailure

URL='https://upload.wikimedia.org/wikipedia/commons/a/ab/Fixture.jpg'
SOURCE='https://commons.wikimedia.org/wiki/File:Fixture.jpg'


def raw_response(data,status=200,headers=None):
    if isinstance(data,dict):data=json.dumps(data).encode()
    return httpx.Response(status,headers=headers or {},stream=httpx.ByteStream(data))


def page(license='Public domain',url=URL):
    return {'title':'File:Fixture.jpg','index':1,'imageinfo':[{'url':url,'descriptionurl':SOURCE,
        'mime':'image/jpeg','width':640,'height':480,'size':100,'extmetadata':{
            'LicenseShortName':{'value':license},'UsageTerms':{'value':license},
            'License':{'value':'pd'},'Artist':{'value':'<b>Original public creator</b>'}}}]}


def test_public_search_download_retains_provenance_and_only_declared_licensed_assets(tmp_path,caplog,capsys):
    import logging
    caplog.set_level(logging.INFO)
    calls=[]
    def answer(request):
        calls.append(request)
        if request.url.host=='commons.wikimedia.org':
            assert request.method=='POST' and not request.url.query
            return raw_response({'query':{'pages':{'1':page()}}})
        return raw_response(b'\xff\xd8\xffsynthetic-jpeg-bytes')
    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        provider=CommonsResearch(consented=True,client=client);items=provider.search('Moon')
        receipt,path=provider.download(items[0],tmp_path)
    assert receipt.source_url==SOURCE and receipt.download_url==URL and receipt.creator=='Original public creator'
    assert receipt.license=='public-domain' and path.stat().st_mode&0o077==0
    assert len(calls)==2 and all(not r.headers.get('Authorization') and not r.headers.get('x-goog-api-key') for r in calls)
    assert 'Moon' not in caplog.text and not capsys.readouterr().out


@pytest.mark.parametrize('license',['CC BY-NC 4.0','CC BY-ND 4.0','CC BY-SA 4.0','Unknown',''])
def test_unsupported_or_ambiguous_rights_are_not_used(license):
    with httpx.Client(transport=httpx.MockTransport(lambda r:raw_response({'query':{'pages':{'1':page(license)}}}))) as client:
        assert CommonsResearch(consented=True,client=client).search('Moon')==[]


@pytest.mark.parametrize('url',['http://127.0.0.1/private','https://169.254.169.254/latest',
    'https://upload.wikimedia.org.evil.invalid/wikipedia/commons/file.jpg','https://user@upload.wikimedia.org/wikipedia/commons/file.jpg',
    'https://upload.wikimedia.org:444/wikipedia/commons/a.jpg','https://upload.wikimedia.org/wikipedia/commons/a.jpg?token=private'])
def test_search_result_urls_cannot_escape_the_fixed_origin(url):
    with httpx.Client(transport=httpx.MockTransport(lambda r:raw_response({'query':{'pages':{'1':page(url=url)}}}))) as client:
        assert CommonsResearch(consented=True,client=client).search('Moon')==[]


def test_consent_and_search_budgets_are_enforced_before_network():
    with pytest.raises(DocumentaryFailure) as failure:CommonsResearch(consented=False)
    assert failure.value.code=='CONSENT_REQUIRED'
    calls=[]
    with httpx.Client(transport=httpx.MockTransport(lambda r:(calls.append(r) or raw_response({'query':{'pages':{}}})))) as client:
        provider=CommonsResearch(consented=True,client=client)
        for _ in range(3):provider.search('Moon')
        with pytest.raises(DocumentaryFailure):provider.search('Moon')
    assert len(calls)==3


def test_redirects_are_not_followed_and_provider_bodies_are_not_leaked(caplog,capsys):
    calls=[]
    def answer(request):calls.append(request);return raw_response(b'private provider body',302,{'Location':'http://127.0.0.1/private'})
    with httpx.Client(transport=httpx.MockTransport(answer),follow_redirects=True) as client:
        with pytest.raises(DocumentaryFailure) as failure:CommonsResearch(consented=True,client=client).search('Moon')
    assert len(calls)==1 and 'private provider body' not in str(failure.value)+caplog.text+capsys.readouterr().out


def test_model_cannot_forge_license_metadata_or_download_arbitrary_candidate(tmp_path):
    calls=[]
    with httpx.Client(transport=httpx.MockTransport(lambda r:(calls.append(r) or raw_response({'query':{'pages':{'1':page()}}})))) as client:
        provider=CommonsResearch(consented=True,client=client);candidate=provider.search('Moon')[0]
        candidate['creator']='Invented attribution'
        with pytest.raises(DocumentaryFailure) as failure:provider.download(candidate,tmp_path)
    assert failure.value.code=='RIGHTS_UNCONFIRMED' and len(calls)==1


def test_research_context_is_cited_data_not_a_claim_of_fact_verification():
    def answer(request):
        assert request.url.host=='en.wikipedia.org'
        return raw_response({'query':{'search':[{'title':'Moon','snippet':'A <b>public</b> source excerpt.'}]}})
    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        notes=CommonsResearch(consented=True,client=client).search_context('Moon')
    assert notes==[{'title':'Moon','excerpt':'A public source excerpt.','source_url':'https://en.wikipedia.org/wiki/Moon'}]


def test_live_commons_tracking_is_removed_without_using_unapproved_thumbnail_host():
    fixture=page(url=URL+'?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original')
    fixture['imageinfo'][0]['thumburl']='https://thumb.wikimedia.org/not-approved.jpg'
    with httpx.Client(transport=httpx.MockTransport(lambda r:raw_response({'query':{'pages':{'1':fixture}}}))) as client:
        assert CommonsResearch(consented=True,client=client).search('Moon')[0]['url']==URL


def test_oversized_original_image_is_rejected_before_download():
    fixture=page();fixture['imageinfo'][0]['size']=8388609
    with httpx.Client(transport=httpx.MockTransport(lambda r:raw_response({'query':{'pages':{'1':fixture}}}))) as client:
        assert CommonsResearch(consented=True,client=client).search('Moon')==[]


def test_oversized_original_dimensions_are_rejected_before_download():
    fixture=page();fixture['imageinfo'][0]['width']=5000
    with httpx.Client(transport=httpx.MockTransport(lambda r:raw_response({'query':{'pages':{'1':fixture}}}))) as client:
        assert CommonsResearch(consented=True,client=client).search('Moon')==[]
