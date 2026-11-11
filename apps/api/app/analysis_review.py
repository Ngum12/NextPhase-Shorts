"""Self-contained private review page. Untrusted transcript is text, never HTML."""
import base64
import hashlib
import html
import json
from .analysis_plan import planning_edl
from .analysis_annotations import fingerprint, validate_review

STYLE = '''body{font:16px system-ui;max-width:980px;margin:40px auto;padding:0 20px;color:#172329;background:#f7fafb}h1{font-size:30px}.notice{padding:16px;background:#fff4d3;border-radius:10px}button{padding:12px;margin:6px 6px 6px 0;cursor:pointer;border:1px solid #bccbd1;border-radius:8px;background:white}button[aria-pressed="true"]{background:#123c4a;color:white}.words{line-height:2.2;background:white;padding:18px;border-radius:10px}.word{padding:2px}.selected{background:#c3f4e6}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e9eff1;padding:16px;border-radius:8px}small{color:#4b6069}'''
STYLE += '''.word{font:inherit;margin:2px;padding:3px 5px}.word.selected{background:#c3f4e6;color:#172329}.word.sentence-end{border-bottom:4px solid #123c4a}.word.sentence-end::after{content:' ⏹'}.confirm-word{display:block;padding:6px}button:disabled{opacity:.5;cursor:default}#review-status{font-weight:bold}'''
SCRIPT = '''const data=JSON.parse(document.getElementById('data').dataset.json);
const proposal=data.proposal, transcript=data.transcript;
document.getElementById('meta').textContent=`${transcript.language.toUpperCase()} · ${transcript.provider} · ${transcript.words.length} words · source ${transcript.source_sha256}`;
document.getElementById('warnings').textContent=proposal.warnings.join(', ') || 'Human review is required.';
const ends=new Set(data.review.sentence_end_words), confirmed=new Set(data.review.confirmed_low_confidence_words);
const wordNodes=transcript.words.map((word,index)=>{const span=document.createElement('button');span.type='button';span.className='word';span.textContent=word.text+' ';span.title=`Word ${index+1} · ${word.start_ms}–${word.end_ms} ms · click to mark/unmark sentence ending`;span.setAttribute('aria-label',`Word ${index+1}: ${word.text}, sentence ending`);span.setAttribute('aria-pressed',String(ends.has(index+1)));span.classList.toggle('sentence-end',ends.has(index+1));span.addEventListener('click',()=>{if(ends.has(index+1)){ends.delete(index+1)}else{ends.add(index+1)}span.setAttribute('aria-pressed',String(ends.has(index+1)));span.classList.toggle('sentence-end',ends.has(index+1));refreshReview()});document.getElementById('words').appendChild(span);return span});
const buttons=[];
let selected=0;
proposal.candidates.forEach((candidate,index)=>{const button=document.createElement('button');button.textContent=`Option ${index+1}: ${(candidate.source_start_ms/1000).toFixed(1)}–${(candidate.source_end_ms/1000).toFixed(1)} s`;
button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>{selected=index;buttons.forEach(b=>b.setAttribute('aria-pressed','false'));button.setAttribute('aria-pressed','true');wordNodes.forEach((node,i)=>node.classList.toggle('selected',i>=candidate.first_word&&i<=candidate.last_word));document.getElementById('details').textContent=JSON.stringify(candidate,null,2)});buttons.push(button);document.getElementById('choices').appendChild(button)});
if(buttons.length){buttons[0].click()}else{document.getElementById('details').textContent='No complete, sufficiently confident sentence window fits. Review or correct the transcript; no edit was invented.'}
const download=document.getElementById('download');download.disabled=!buttons.length;
download.addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data.edls[selected],null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`proposed-edl-option-${selected+1}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
const flags=[];
transcript.words.forEach((word,index)=>{if(word.confidence!==null && word.confidence<0.45){const label=document.createElement('label');label.className='confirm-word';const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=confirmed.has(index+1);checkbox.addEventListener('change',()=>{if(checkbox.checked){confirmed.add(index+1)}else{confirmed.delete(index+1)}refreshReview()});label.appendChild(checkbox);const text=document.createElement('span');text.textContent=` Word ${index+1}: ${word.text} — model score ${word.confidence.toFixed(3)}. I confirmed this word in the original recording.`;label.appendChild(text);document.getElementById('flagged').appendChild(label);flags.push({number:index+1,checkbox})}});
document.getElementById('confirm-all').disabled=!flags.length;
document.getElementById('confirm-all').addEventListener('click',()=>{flags.forEach(flag=>{flag.checkbox.checked=true;confirmed.add(flag.number)});refreshReview()});
const acknowledge=document.getElementById('acknowledge'), exportReview=document.getElementById('export-review');
function refreshReview(){document.getElementById('review-status').textContent=`${ends.size} sentence endings marked · ${confirmed.size} flagged words confirmed. Changes take effect only after you download and replan on the server.`;exportReview.disabled=!(ends.size && acknowledge.checked)}
acknowledge.addEventListener('change',refreshReview);
exportReview.addEventListener('click',()=>{if(exportReview.disabled){return}const annotation={...data.review,acknowledged_original_recording:true,sentence_end_words:[...ends].sort((a,b)=>a-b),confirmed_low_confidence_words:[...confirmed].sort((a,b)=>a-b)};const url=URL.createObjectURL(new Blob([JSON.stringify(annotation,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='transcript-review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
refreshReview();
'''


def review_html(transcript, proposal, *, review=None):
    if proposal.source_sha256 != transcript.source_sha256:
        raise ValueError('Review artifacts reference different sources')
    for candidate in proposal.candidates:
        if candidate.last_word >= len(transcript.words):
            raise ValueError('Candidate references missing words')
    if review is not None:
        review=validate_review(transcript,review)
    if proposal.review_sha256 is not None:
        if (review is None or fingerprint(review)!=proposal.review_sha256
                or fingerprint(transcript)!=proposal.transcript_sha256):
            raise ValueError('Review page annotations differ from proposal')
    annotations=review.model_dump(mode='json') if review is not None else {
        'schema_version':'transcript-review-1','source_sha256':transcript.source_sha256,
        'transcript_sha256':fingerprint(transcript),'acknowledged_original_recording':False,
        'sentence_end_words':[],'confirmed_low_confidence_words':[]}
    payload=json.dumps({'transcript':transcript.model_dump(mode='json'),
                        'proposal':proposal.model_dump(mode='json'),
                        'review':annotations,
                        'edls':[planning_edl(proposal,i) for i in range(len(proposal.candidates))]},ensure_ascii=False)
    def digest(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
    policy=f"default-src 'none'; script-src 'sha256-{digest(SCRIPT)}'; style-src 'sha256-{digest(STYLE)}'; base-uri 'none'; form-action 'none'"
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{html.escape(policy,quote=True)}">
<title>NextPhase — private transcript review</title><style>{STYLE}</style></head><body>
<h1>Transcript &amp; proposed excerpt</h1>
<p class="notice">Experimental private planning. Review the original recording before approving. Timing and model scores do not verify meaning. This page does not render video or add captions.</p>
<small id="meta"></small><p id="warnings"></p><h2>Candidate excerpts</h2><div id="choices"></div>
<pre id="details" aria-live="polite"></pre><button id="download">Download selected proposal</button>
<h2>1. Mark sentence endings</h2><p>Click the last word of each complete sentence. A square and underline mark your selection; click again to undo. Words and timestamps stay unchanged.</p><div id="words" class="words"></div>
<h2>2. Confirm flagged words</h2><p>Check a word only if it matches what you hear in the original recording. Confirmation keeps its original model score and records your separate review.</p>
<div id="flagged"></div><button id="confirm-all">I checked every flagged word — confirm all</button>
<h2>3. Save your review</h2><p><label><input type="checkbox" id="acknowledge"> I compared these sentence endings and word confirmations with my original recording.</label></p>
<p id="review-status" aria-live="polite"></p><button id="export-review" disabled>Download transcript review</button>
<p>Timing is estimated or operator supplied. This private page contains transcript text; store and delete it with the source's consent/retention policy.</p>
<div id="data" hidden data-json="{html.escape(payload,quote=True)}"></div><script>{SCRIPT}</script></body></html>'''
