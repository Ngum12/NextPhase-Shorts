"""Render one acknowledged proposal candidate for private source-video review."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--proposal', required=True, help='Saved proposal.json, not an exported EDL')
    parser.add_argument('--candidate', type=int, required=True, help='Review option number, starting at 1')
    parser.add_argument('--output', required=True, help='New private directory')
    parser.add_argument('--acknowledge-preview', action='store_true',
                        help='I reviewed the proposed text; I will review the rendered cut')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        from app.analysis_preview import preview
        print(json.dumps(preview(source=args.source, proposal=args.proposal,
              candidate=args.candidate, output=args.output, acknowledge=args.acknowledge_preview)))
        return 0
    except Exception as error:
        from pydantic import ValidationError
        codes = {
            'Preview source identity differs': 'source_identity_mismatch',
            'Preview source duration differs': 'source_duration_mismatch',
            'Review acknowledgement required': 'review_acknowledgement_required',
            'Choose an available candidate': 'candidate_unavailable',
            'Preview output failed validation': 'output_validation_failed',
            'Preview pilot requires development/test mode': 'development_mode_required',
            'Preview pilot is not enabled in required worker mode': 'worker_mode_refused',
        }
        reason = ('output_exists' if isinstance(error, FileExistsError) else
                  'invalid_proposal' if isinstance(error, ValidationError) else
                  codes.get(str(error), 'unclassified'))
        print(json.dumps({'ok': False, 'issue': 'preview_refused_or_failed',
                          'reason_code': reason,
                          'inputs_preserved': True, 'private_text_printed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
