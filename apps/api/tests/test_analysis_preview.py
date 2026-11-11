"""Private operator preview: real FFmpeg cut plus admission/cleanup checks."""
import json
import math
import os
import subprocess

import pytest

from app import analysis_preview as module
from app.analysis_plan import Candidate, Proposal
from app.local_transcription import file_digest
from app.media import probe_video


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-f', 'lavfi', '-i',
        'testsrc2=size=160x90:rate=15', '-f', 'lavfi', '-i',
        r'aevalsrc=sin(2*PI*if(lt(t\,1)\,440\,880)*t):s=16000', '-t', '7', '-c:v', 'libx264',
        '-threads', '2', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)],
        check=True, timeout=30)
    candidate = Candidate(first_word=0, last_word=1, source_start_ms=1010,
        source_end_ms=6010, output_frames=150, confidence=.9, speech_density=.9, score=.8)
    plan = Proposal(source_sha256=file_digest(source),
        source_duration_ms=math.ceil(probe_video(source)['duration'] * 1000), language='en',
        requested_seconds=15, candidates=(candidate,), warnings=('estimated_timestamps',))
    proposal = tmp_path / 'proposal.json'
    proposal.write_text(plan.model_dump_json())
    return source, proposal


def call(inputs, tmp_path, **kwargs):
    source, proposal = inputs
    return module.preview(**dict(source=source, proposal=proposal,
        candidate=1, output=tmp_path/'preview', acknowledge=True, **kwargs))


@pytest.mark.parametrize('extra_ms', [0, 40])
def test_actual_offset_render_is_private_frame_exact_and_source_bound(inputs, tmp_path, extra_ms):
    source, proposal = inputs
    plan = json.loads(proposal.read_text())
    plan['candidates'][0]['source_end_ms'] += extra_ms
    frames = (5000 + extra_ms)*30//1000
    plan['candidates'][0]['output_frames'] = frames
    proposal.write_text(json.dumps(plan))
    before = file_digest(source)
    report = call(inputs, tmp_path)
    assert report['output_frames'] == frames
    assert report['source_start_ms'] == 1010
    assert report['width'] == 1080 and report['height'] == 1920
    assert report['duration_seconds'] == pytest.approx(frames/30, abs=.034)
    assert report['human_review_required'] and not report['live_app_changed']
    assert report['preview_sha256'] == file_digest(tmp_path/'preview/preview.mp4')
    assert file_digest(source) == before
    assert not any(p.is_dir() for p in (tmp_path/'preview').iterdir())
    if os.name == 'posix':
        assert (tmp_path/'preview').stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in (tmp_path/'preview').iterdir())
    # Original AAC track remains present after the cut.
    raw = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'a',
        '-show_entries', 'stream=codec_name', '-of', 'json', str(tmp_path/'preview/preview.mp4')])
    assert json.loads(raw)['streams'][0]['codec_name'] == 'aac'
    # The first second is 440 Hz and the selected interval is 880 Hz. Verify
    # actual audio at the cut rather than just trusting the reported offset.
    import struct
    pcm = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i',
        str(tmp_path/'preview/preview.mp4'), '-t', '0.1', '-vn', '-ar', '16000',
        '-ac', '1', '-f', 's16le', 'pipe:1'])
    samples = struct.unpack('<'+'h'*(len(pcm)//2), pcm)
    def power(hz):
        return sum(s*math.sin(2*math.pi*hz*i/16000) for i,s in enumerate(samples))**2 \
             + sum(s*math.cos(2*math.pi*hz*i/16000) for i,s in enumerate(samples))**2
    assert power(880) > 10*power(440)


@pytest.mark.parametrize('change', ['digest', 'range', 'frames', 'extra', 'edl'])
def test_invalid_or_unbound_plan_preserves_inputs_and_leaves_no_output(inputs, tmp_path, change):
    source, path = inputs
    plan = json.loads(path.read_text())
    if change == 'digest': plan['source_sha256'] = '0'*64
    elif change == 'range': plan['candidates'][0]['source_end_ms'] = 8000
    elif change == 'frames': plan['candidates'][0]['output_frames'] = 151
    elif change == 'extra': plan['command'] = 'untrusted data'
    else: plan = {'schema_version': 'analysis-1', 'render_supported': False}
    path.write_text(json.dumps(plan))
    before = file_digest(source)
    with pytest.raises(Exception): call(inputs, tmp_path)
    assert source.exists() and path.exists() and file_digest(source) == before
    assert not (tmp_path/'preview').exists()


def test_existing_output_is_preserved(inputs, tmp_path):
    output = tmp_path/'preview'; output.mkdir()
    (output/'keep').write_text('preserve')
    with pytest.raises(FileExistsError): call(inputs, tmp_path)
    assert (output/'keep').read_text() == 'preserve'


@pytest.mark.parametrize('mode', ['production', 'staging', 'sandbox', 'no_ack', 'bad_candidate'])
def test_operator_guards(inputs, tmp_path, monkeypatch, mode):
    source, proposal = inputs
    if mode in ('production', 'staging'): monkeypatch.setenv('APP_ENV', mode)
    if mode == 'sandbox': monkeypatch.setenv('WORKER_REQUIRE_SANDBOX', 'true')
    with pytest.raises(RuntimeError):
        module.preview(source=source, proposal=proposal, output=tmp_path/'preview',
            candidate=0 if mode == 'bad_candidate' else 1, acknowledge=mode != 'no_ack')
    assert not (tmp_path/'preview').exists()


def test_failed_render_removes_only_new_output(inputs, tmp_path, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError('fixture failure')
    monkeypatch.setattr(module, 'render_excerpt', fail)
    with pytest.raises(RuntimeError): call(inputs, tmp_path)
    assert all(path.exists() for path in inputs)
    assert not (tmp_path/'preview').exists()


def test_sixty_second_silent_source_renders_without_exceeding_cap(tmp_path):
    source = tmp_path/'silent.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-f', 'lavfi', '-i',
        'color=c=blue:size=160x90:rate=15', '-t', '61', '-c:v', 'libx264', '-threads',
        '2', '-pix_fmt', 'yuv420p', str(source)], check=True, timeout=30)
    selected = Candidate(first_word=0, last_word=1, source_start_ms=0,
        source_end_ms=60000, output_frames=1800, confidence=None, speech_density=.9, score=.8)
    plan = Proposal(source_sha256=file_digest(source), source_duration_ms=61000,
        language='fr', requested_seconds=60, candidates=(selected,), warnings=('manual_transcript',))
    proposal = tmp_path/'proposal.json'; proposal.write_text(plan.model_dump_json())
    report = call((source, proposal), tmp_path)
    assert report['output_frames'] == 1800 and report['duration_seconds'] <= 60
