"""Public synthetic fixtures only: these do not test a running Herbie model."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('contract', Path(__file__).resolve().parents[1] / 'agents/check_contract.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class ContractTests(unittest.TestCase):
    def check(self, **changes):
        response = dict(contract_version=1, network_attempts=0, citations=['synthetic-A'],
                        retrieved_ids=['synthetic-A'], fact_ids=['fixture-fact-A'])
        response.update(changes)
        return c.check_response(response, expected_fact='fixture-fact-A',
                                expected_source='synthetic-A', known_sources={'synthetic-A', 'synthetic-B'})

    def test_supported_fixture(self):
        self.assertEqual(self.check(), [])

    def test_network_attempt_blocks_offline(self):
        self.assertIn('offline', self.check(network_attempts=1))

    def test_missing_network_instrumentation_cannot_pass(self):
        self.assertIn('offline', self.check(network_attempts=None))

    def test_unknown_citation_blocks_accuracy(self):
        self.assertIn('source_accuracy', self.check(citations=['invented']))

    def test_irrelevant_retrieval_blocks(self):
        self.assertIn('retrieval', self.check(retrieved_ids=['synthetic-B']))

    def test_wrong_fact_or_uncited_fact_blocks(self):
        self.assertIn('grounding', self.check(fact_ids=['wrong']))
        self.assertIn('grounding', self.check(citations=['synthetic-B']))

    def test_incompatible_contract_blocks(self):
        self.assertIn('contract_version', self.check(contract_version=2))

    def test_malformed_envelope_blocks(self):
        self.assertEqual(c.check_response(None, expected_fact='x', expected_source='a', known_sources={'a'}), ['invalid_envelope'])
