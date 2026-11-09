"""Combine tested software evidence with explicit external approval gaps."""
import hashlib
import json
from pathlib import Path

GATES={'hosting_budget','privacy_terms','license_review','provider_terms','offsite_key_journal_custody',
       'actual_provider_costs_and_quotas','actual_staging_device_acceptance','trusted_certificate_and_tls_edge','private_storage_and_least_privilege'}
CHECKS={'encrypted_restore','private_https_renderer','monitoring_delivery','budget_admission_gate','regression_suite'}


def review(checks,approvals):
    if set(checks)!=CHECKS or any(type(value) is not bool for value in checks.values()) or set(approvals)!=GATES:raise ValueError('Unknown release evidence')
    accepted={}
    for name,value in approvals.items():
        accepted[name]=bool(isinstance(value,dict) and set(value)=={'approved','evidence_sha256','reviewed_at'} and value['approved'] is True
            and isinstance(value['evidence_sha256'],str) and len(value['evidence_sha256'])==64 and set(value['evidence_sha256'])<=set('0123456789abcdef')
            and value['evidence_sha256']!='0'*64 and isinstance(value['reviewed_at'],str) and value['reviewed_at'])
    return {'version':1,'software_checks':checks,'external_operator_attestations':accepted,'release_ready':all(checks.values()) and all(accepted.values()),
        'missing_external_gates':sorted(name for name,value in accepted.items() if not value),
        'scope':'local software acceptance plus unverified operator attestations; not legal certification/provider invoice verification'}
