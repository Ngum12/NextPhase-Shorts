"""Fixed, privacy-safe diagnosis categories for private English analysis.

Do not include model text, filenames, paths, stderr, return codes, account IDs,
or raw exception detail in a durable job status or mobile error message.
"""
from .media import MediaError

CODES = frozenset({
    'ASR_PROCESS_FAILED',
    'ASR_DEADLINE_EXCEEDED',
    'ASR_OUTPUT_INVALID',
    'ASR_WORD_TIMING_REJECTED',
    'ASR_TRANSCRIPT_REJECTED',
})


class AsrFailure(MediaError):
    """Only closed codes may cross the worker -> database -> owner boundary."""

    def __init__(self, code):
        if code not in CODES:
            raise ValueError('Unsupported English analysis failure code')
        self.code = code
        super().__init__('English transcription failed')
