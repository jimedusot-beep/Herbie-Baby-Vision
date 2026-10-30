"""Synthetic adapter acceptance contract; never import course or memory content.

The caller must independently instrument network attempts. This checks fixture
responses, not scientific truth or the honesty of an untrusted adapter.
"""

def check_response(response, *, expected_fact, expected_source, known_sources):
    failures = []
    if not isinstance(response, dict):
        return ['invalid_envelope']
    if type(response.get('contract_version')) is not int or response['contract_version'] != 1:
        failures.append('contract_version')
    if type(response.get('network_attempts')) is not int or response['network_attempts'] != 0:
        failures.append('offline')
    citations = response.get('citations')
    retrieved = response.get('retrieved_ids')
    if (not isinstance(citations, list) or not citations or
            any(not isinstance(key, str) or key not in known_sources for key in citations)):
        failures.append('source_accuracy')
    if (not isinstance(retrieved, list) or expected_source not in retrieved or
            any(not isinstance(key, str) or key not in known_sources for key in retrieved)):
        failures.append('retrieval')
    facts = response.get('fact_ids')
    if not isinstance(facts, list) or facts != [expected_fact] or not isinstance(citations, list) or expected_source not in citations:
        failures.append('grounding')
    return failures
