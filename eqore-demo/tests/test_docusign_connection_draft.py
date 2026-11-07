"""Connection tests use durable isolated state and mocked provider transport only."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
import urllib.parse

from paperwork_api import PaperworkService
from paperwork_connectors import ConnectorError, PaperworkConnectors
from storage import Conflict, Store
from tests.test_paperwork_connectors import FakeTransport


class ConnectionDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name + '/isolated.sqlite3')
        self.service = PaperworkService(self.store, None, {'authenticated': False, 'detail': 'Test'})
        self.token = self.service.login('pm_jordan')['token']

    def tearDown(self):
        self.tmp.cleanup()

    def record(self):
        return self.store.read_workspace('paperwork')

    def connect(self, *responses, account='account-1'):
        fake = FakeTransport({'accountId': account}, *responses)
        client = PaperworkConnectors({'EQORE_DOCUSIGN_ACCESS_TOKEN': 'private-token',
                                     'EQORE_DOCUSIGN_ACCOUNT_ID': account}, fake)
        client.test_connection('docusign')
        self.service.session_connectors[self.token] = client
        return fake

    def create(self, **fields):
        payload = {'operation': 'create_connection_draft', 'provider': 'docusign',
                   'email': 'test.signer@gmail.com', 'expected_version': self.record()['version']}
        payload.update(fields)
        return self.service.connector_action(self.token, payload)

    def test_real_draft_payload_is_fixed_unsent_and_never_changes_projects(self):
        original = copy.deepcopy(self.record()['state']['projects'])
        fake = self.connect({'envelopeTransactionStatuses': []}, {'envelopeId': 'test-envelope', 'status': 'created'})
        result = self.create(body='Approve construction', project_id='summit_precision',
                             recipients=[{'email': 'unwanted@example.com'}])
        sent = fake.calls[-1]['body']
        self.assertEqual('created', sent['status'])
        self.assertEqual(1, len(sent['recipients']['signers']))
        self.assertEqual('Test signer', sent['recipients']['signers'][0]['name'])
        self.assertEqual('test.signer@gmail.com', sent['recipients']['signers'][0]['email'])
        text = base64.b64decode(sent['documents'][0]['documentBase64']).decode()
        self.assertIn('not an agreement, approval, permit', text)
        self.assertNotIn('Approve construction', text)
        self.assertEqual(original, self.record()['state']['projects'])
        self.assertFalse(result['connector_result']['sent'])
        self.assertFalse(result['connector_result']['project_records_changed'])
        self.assertEqual('test-envelope', result['connectors']['latest_connection_test']['envelope_id'])
        self.assertNotIn('private-token', repr(result))

    def test_repeat_and_restart_return_same_completed_request_without_provider_write(self):
        fake = self.connect({'envelopeTransactionStatuses': []}, {'envelopeId': 'one-envelope', 'status': 'created'})
        first = self.create()
        second = self.create()
        self.assertEqual(first['connector_result']['envelope_id'], second['connector_result']['envelope_id'])
        self.assertTrue(second['connector_result']['already_created'])
        self.assertEqual(1, sum(c['method'] == 'POST' for c in fake.calls))
        self.service = PaperworkService(self.store, None, {'authenticated': False, 'detail': 'Test'})
        self.token = self.service.login('pm_jordan')['token']
        restarted = self.connect()
        self.assertEqual('one-envelope', self.create()['connector_result']['envelope_id'])
        self.assertEqual(['GET'], [c['method'] for c in restarted.calls])

    def test_ambiguous_timeout_recovers_same_transaction_without_new_post(self):
        fake = self.connect({'envelopeTransactionStatuses': []}, TimeoutError('private response'))
        with self.assertRaises(ConnectorError) as ctx:
            self.create()
        self.assertTrue(ctx.exception.ambiguous)
        pending = self.record()['state']['connection_tests']['pm_jordan']['account-1']
        self.assertEqual('needs_reconciliation', pending['status'])
        transaction = fake.calls[-1]['body']['transactionId']
        def existing(call):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(call['url']).query)
            self.assertEqual([transaction], query['transaction_ids'])
            return {'envelopeTransactionStatuses': [{'transactionId': transaction,
                    'envelopeId': 'recovered-envelope', 'status': 'created'}]}
        recovered = self.connect(existing)
        result = self.create()
        self.assertTrue(result['connector_result']['recovered'])
        self.assertEqual(['GET', 'GET'], [c['method'] for c in recovered.calls])
        self.assertNotIn('error', result['connectors']['latest_connection_test'])

    def test_email_change_cannot_bypass_pending_request_identity(self):
        fake = self.connect({'envelopeTransactionStatuses': []}, TimeoutError())
        with self.assertRaises(ConnectorError):
            self.create()
        count = len(fake.calls)
        with self.assertRaises(ValueError):
            self.create(email='different@gmail.com', request_id='fresh-request')
        self.assertEqual(count, len(fake.calls))

    def test_recovered_externally_sent_envelope_is_not_reported_as_an_unsent_draft(self):
        def existing(call):
            transaction = urllib.parse.parse_qs(urllib.parse.urlsplit(call['url']).query)['transaction_ids'][0]
            return {'envelopeTransactionStatuses': [{'transactionId': transaction,
                    'envelopeId': 'externally-sent', 'status': 'sent'}]}
        fake = self.connect(existing)
        result = self.create()['connector_result']
        self.assertTrue(result['sent'])
        self.assertFalse(result['sent_by_application'])
        self.assertEqual('sent', result['envelope_status'])
        self.assertEqual(['GET', 'GET'], [c['method'] for c in fake.calls])

    def test_account_and_pm_boundaries_have_separate_test_history(self):
        first = self.connect({'envelopeTransactionStatuses': []}, {'envelopeId': 'account-one-envelope', 'status': 'created'})
        self.create()
        first_transaction = first.calls[-1]['body']['transactionId']
        second = self.connect({'envelopeTransactionStatuses': []}, {'envelopeId': 'account-two-envelope', 'status': 'created'}, account='account-2')
        self.assertIsNone(self.service.connector_status(self.token)['latest_connection_test'])
        self.create()
        self.assertNotEqual(first_transaction, second.calls[-1]['body']['transactionId'])
        self.assertEqual(2, len(self.record()['state']['connection_tests']['pm_jordan']))
        self.token = self.service.login('pm_casey')['token']
        self.connect(account='account-1')
        self.assertIsNone(self.service.connector_status(self.token)['latest_connection_test'])

    def test_invalid_provider_email_or_unchecked_connection_never_writes(self):
        original = self.record()
        for changes in ({'provider': 'gmail'}, {'email': 'bad'}, {'email': 'test@example.com'}, {}):
            with self.assertRaises(ValueError):
                self.create(**changes)
        self.assertEqual(original, self.record())

    def test_stale_version_is_rejected_before_any_envelope_lookup(self):
        fake = self.connect()
        with self.assertRaises(Conflict):
            self.create(expected_version=-1)
        self.assertEqual(1, len(fake.calls))

    def test_pending_request_outside_recovery_window_cannot_create_duplicate(self):
        fake = self.connect({'envelopeTransactionStatuses': []}, TimeoutError())
        with self.assertRaises(ConnectorError):
            self.create()
        record = self.record()
        request_id = record['state']['connection_tests']['pm_jordan']['account-1']['request_id']
        record['state']['external_requests'][request_id]['at'] = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        self.store.write_workspace('paperwork', record['state'], record['version'])
        count = len(fake.calls)
        with self.assertRaisesRegex(ValueError, 'recovery window'):
            self.create()
        self.assertEqual(count, len(fake.calls))


if __name__ == '__main__':
    unittest.main()
