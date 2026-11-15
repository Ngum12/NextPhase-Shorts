"""Raw native output is discarded; only bounded numeric counters survive."""
from app.resource_measure import EncodeProgress


def test_chunked_progress_ignores_private_unknown_lines_and_invalid_numbers(caplog,capsys):
    progress=EncodeProgress()
    progress.feed(b'frame=12\nfps=4.')
    progress.feed(b'25\nfilename=private recording\nfps=NaN\nframe=1801\nframe=-1\nframe=private transcript\nfps=inf\n')
    assert progress.attributes()=={'frames':12,'frames_per_second':4.25}
    assert not caplog.text and not capsys.readouterr().out


def test_oversized_lines_and_frame_counts_remain_bounded():
    progress=EncodeProgress()
    for _ in range(100):
        progress.feed(b'x'*4096)
        assert len(progress.pending)<=128
    progress.feed(b'frame=999\nframe=885\nfps=29.98\nframe=0\n')
    assert progress.attributes()=={'frames':885,'frames_per_second':29.98}
