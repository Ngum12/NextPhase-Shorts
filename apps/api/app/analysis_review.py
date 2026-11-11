"""Self-contained private review page. Untrusted transcript is text, never HTML."""
import base64
import hashlib
import html
import json
from .analysis_plan import planning_edl

STYLE = '''body{font:16px system-ui;max-width:980px;margin:40px auto;padding:0 20px;color:#172329;background:#f7fafb}h1{font-size:30px}.notice{padding:16px;background:#fff4d3;border-radius:10px}button{padding:12px;margin:6px 6px 6px 0;cursor:pointer;border:1px solid #bccbd1;border-radius:8px;background:white}button[aria-pressed="true"]{background:#123c4a;color:white}.words{line-height:2.2;background:white;padding:18px;border-radius:10px}.word{padding:2px}.selected{background:#c3f4e6}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e9eff1;padding:16px;border-radius:8px}small{color:#4b6069}'''
SCRIPT = '''const data=JSON.parse(document.getElementById('data').dataset.json);
const proposal=data.proposal, transcript=data.transcript;
document.getElementById('meta').textContent=`${transcript.language.toUpperCase()} · ${transcript.provider} · ${transcript.words.length} words · source ${transcript.source_sha256}`;
document.getElementById('warnings').textContent=proposal.warnings.join(', ') || 'Human review is required.';
const wordNodes=transcript.words.map(word=>{const span=document.createElement('span');span.className='word';span.textContent=word.text+' ';span.title=`${word.start_ms}–${word.end_ms} ms`;document.getElementById('words').appendChild(span);return span});
const buttons=[];
let selected=0;
proposal.candidates.forEach((candidate,index)=>{const button=document.createElement('button');button.textContent=`Option ${index+1}: ${(candidate.source_start_ms/1000).toFixed(1)}–${(candidate.source_end_ms/1000).toFixed(1)} s`;
button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>{selected=index;buttons.forEach(b=>b.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');wordNodes.forEach((node,i)=>node.classList.toggle('selected',i>=candidate.first_word&&i<=candidate.last_word));document.getElementById('details').textContent=JSON.stringify(candidate,null,2)});buttons.push(button);document.getElementById('choices').appendChild(button)});
if(buttons.length){buttons[0].click()}else{document.getElementById('details').textContent='No complete, sufficiently confident sentence window fits. Review or correct the transcript; no edit was invented.'}
const download=document.getElementById('download');download.disabled=!buttons.length;
download.addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data.edls[selected],null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`proposed-edl-option-${selected+1}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
'''


def review_html(transcript, proposal):
    if proposal.source_sha256 != transcript.source_sha256:
        raise ValueError('Review artifacts reference different sources')
    for candidate in proposal.candidates:
        if candidate.last_word >= len(transcript.words):
            raise ValueError('Candidate references missing words')
    payload=json.dumps({'transcript':transcript.model_dump(mode='json'),
                        'proposal':proposal.model_dump(mode='json'),
                        'edls':[planning_edl(proposal,i) for i in range(len(proposal.candidates))]},ensure_ascii=False)
    def digest(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
    policy=f"default-src 'none'; script-src 'sha256-{digest(SCRIPT)}'; style-src 'sha256-{digest(STYLE)}'; base-uri 'none'; form-action 'none'"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{html.escape(policy,quote=True)}">
<title>NextPhase — private transcript review</title><style>{STYLE}</style></head><body>
<h1>Transcript &amp; proposed excerpt</h1>
<p class="notice">Experimental local planning only. Sentence windows are ranked by timing, probability and speech density—not verified story quality. Review the original recording before approving. No render or caption feature is enabled.</p>
<small id="meta"></small><p id="warnings"></p><h2>Candidate excerpts</h2><div id="choices"></div>
<pre id="details" aria-live="polite"></pre><button id="download">Download selected proposal</button><h2>Transcript</h2><div id="words" class="words"></div>
<p>Timing is estimated or operator supplied. This private page contains transcript text; store and delete it with the source's consent/retention policy.</p>
<div id="data" hidden data-json="{html.escape(payload,quote=True)}"></div><script>{SCRIPT}</script></body></html>'''
