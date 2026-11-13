"""Shared finite analysis/queue budgets; ASR keeps its separate configured cap."""

# Scaling a tiny output still requires decoding the full-resolution input.
VISUAL_TIMEOUT_SECONDS = 120
# Audio extraction (120s), source probe (30s), copy/planning/publication margin (30s).
ANALYSIS_OVERHEAD_SECONDS = VISUAL_TIMEOUT_SECONDS + 180
# Let the database hard deadline/cancellation settle before Arq aborts dispatch.
BROKER_ANALYSIS_OVERHEAD_SECONDS = ANALYSIS_OVERHEAD_SECONDS + 60
