"""Fixed, privacy-safe diagnosis categories for private English analysis.

Do not include model text, filenames, paths, stderr, return codes, account IDs,
or raw exception detail in a durable job status or mobile error message.
"""
from .media import MediaError

TIMING_CODES = frozenset({
    'ASR_WORD_TIMING_REJECTED',  # Legacy statuses remain readable.
    'ASR_OFFSETS_MISSING',
    'ASR_OFFSETS_INVALID',
    'ASR_OFFSETS_OUT_OF_SOURCE',  # Legacy statuses.
    'ASR_OFFSETS_BEFORE_SOURCE',
    'ASR_OFFSETS_AFTER_SOURCE',
    'ASR_OFFSETS_BEYOND_BOTH_BOUNDS',
    'ASR_WORD_ORDER_BACKWARD',
    'ASR_WORD_OVERLAP_EXCESSIVE',
    'ASR_TIMING_REPAIR_EXCEEDED',
})

CODES = TIMING_CODES | frozenset({
    'ASR_PROCESS_FAILED',
    'ASR_DEADLINE_EXCEEDED',
    'ASR_OUTPUT_INVALID',
    'ASR_TRANSCRIPT_REJECTED',
})


class AsrFailure(MediaError):
    """Only closed codes may cross the worker -> database -> owner boundary."""

    def __init__(self, code):
        if code not in CODES:
            raise ValueError('Unsupported English analysis failure code')
        self.code = code
        super().__init__('English transcription failed')
