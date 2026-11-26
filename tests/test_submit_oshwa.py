"""Offline checks for the certification submission boundary and explicit consent."""

import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class OshwaSubmissionTests(unittest.TestCase):
    def setUp(self):
        script = ROOT / 'scripts/submit-oshwa.py'
        self.assertTrue(script.is_file(), 'OSHWA submission script is not implemented')
        spec = importlib.util.spec_from_file_location('submit_oshwa', script)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.payload_file = Path(self.temp.name) / 'application.json'
        self.module.DEFAULT_TOKEN_FILE = Path(self.temp.name) / 'fallback-token'
        self.payload = {
            'responsiblePartyType': 'Individual', 'responsibleParty': 'Test Applicant',
            'country': 'Test Country', 'privateContact': 'test@example.com',
            'projectName': 'REMAKE', 'projectVersion': '1.0',
            'projectWebsite': 'https://example.com/remake',
            'documentationUrl': 'https://example.com/remake/v1.0',
            'primaryType': 'Electronics', 'hardwareLicense': 'CERN',
            'softwareLicense': 'MIT', 'documentationLicense': 'Other',
            'availableFileFormat': True, 'agreementTerms': True,
            'explanationCertificationTerms': 'N/A: I agree to all five certification mark terms.',
            'certificationMarkTerms': {
                key: {'agreement': True} for key in [
                    'accurateContactInformation', 'complianceWithOfficialCertificationGuidelines',
                    'oshwaCertificationMark', 'violationsEnforcement', 'responsibility',
                ]
            },
        }
        for field in ['noCommercialRestriction', 'noDocumentationRestriction',
                      'openHardwareComponents', 'creatorContribution', 'noUseRestriction',
                      'redistributedWork', 'noSpecificProduct', 'noComponentRestriction',
                      'technologyNeutral']:
            self.payload[field] = True
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                size = int(self.headers.get('Content-Length', 0))
                owner.requests.append((self.command, self.path, self.headers.get('Authorization'), self.rfile.read(size)))
                self.send_response(owner.status)
                if owner.truncated:
                    self.send_header('Content-Length', str(len(owner.response) + 100))
                if owner.status == 302:
                    self.send_header('Location', '/redirect-target')
                self.end_headers()
                self.wfile.write(owner.response)

            do_GET = handle_request
            do_POST = handle_request

            def log_message(self, *args):
                pass

        self.status, self.response = 200, b'{"success": true, "project": {"projectName": "REMAKE"}}'
        self.truncated = False
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.module.API_BASE = f'http://127.0.0.1:{self.server.server_port}'

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_cli(self, args, token='test-secret-token'):
        self.payload_file.write_text(json.dumps(self.payload))
        stdout, stderr = io.StringIO(), io.StringIO()
        env = {'OSHWA_API_TOKEN': token}
        with patch.dict(os.environ, env), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.module.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_preview_needs_no_token_and_makes_no_request(self):
        self.payload['agreementTerms'] = False
        result, stdout, stderr = self.run_cli([str(self.payload_file)], token='')
        self.assertEqual(result, 0, stderr)
        self.assertEqual(json.loads(stdout), self.payload)
        self.assertEqual(self.requests, [])

    def test_submit_posts_exact_reviewed_payload_once_with_bearer_auth(self):
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertEqual(result, 0, stderr)
        self.assertEqual(len(self.requests), 1)
        method, path, auth, body = self.requests[0]
        self.assertEqual((method, path, auth), ('POST', '/api/projects', 'Bearer test-secret-token'))
        self.assertEqual(json.loads(body), self.payload)
        self.assertIn('not certification approval', stdout)
        self.assertNotIn('test-secret-token', stdout + stderr)

    def test_missing_token_never_submits(self):
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'], token='')
        self.assertNotEqual(result, 0)
        self.assertIn('OSHWA_API_TOKEN', stderr)
        self.assertEqual(self.requests, [])

    def test_missing_or_string_consent_never_submits(self):
        for consent in [False, 'true', None]:
            with self.subTest(consent=consent):
                self.payload['agreementTerms'] = consent
                result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
                self.assertNotEqual(result, 0)
                self.assertEqual(self.requests, [])

    def test_every_named_mark_term_needs_explicit_agreement(self):
        self.payload['certificationMarkTerms']['responsibility']['agreement'] = False
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('responsibility', stderr)
        self.assertEqual(self.requests, [])

    def test_empty_mark_explanation_is_rejected_before_the_known_api_validation_error(self):
        self.payload['explanationCertificationTerms'] = ''
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('explanationCertificationTerms', stderr)
        self.assertEqual(self.requests, [])

    def test_conditional_binding_party_is_required_for_a_company(self):
        self.payload['responsiblePartyType'] = 'Company'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('bindingParty', stderr)
        self.assertEqual(self.requests, [])

    def test_documented_negative_declaration_with_explanation_is_preserved(self):
        self.payload['openHardwareComponents'] = False
        self.payload['explanationOhwc'] = 'Some third-party components are proprietary; see documentation.'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertEqual(result, 0, stderr)
        self.assertEqual(json.loads(self.requests[0][3]), self.payload)

    def test_options_fetches_choices_without_posting_an_application(self):
        self.response = b'{"hardwareLicenseOptions": ["CERN"]}'
        result, stdout, stderr = self.run_cli(['--options'])
        self.assertEqual(result, 0, stderr)
        self.assertEqual(self.requests[0][:2], ('GET', '/api/options'))
        self.assertEqual(json.loads(stdout), {'hardwareLicenseOptions': ['CERN']})

    def test_http_errors_are_reported_without_retry_or_token_disclosure(self):
        self.status = 422
        self.response = b'{"error": "invalid licence; test-secret-token"}'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('422', stderr)
        self.assertIn('invalid licence', stderr)
        self.assertNotIn('test-secret-token', stdout + stderr)
        self.assertEqual(len(self.requests), 1)

    def test_redirects_are_not_followed_with_credentials(self):
        self.status, self.response = 302, b'Unexpected redirect'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertEqual(len(self.requests), 1)

    def test_200_with_success_false_is_not_reported_as_submitted(self):
        self.response = b'{"success": false}'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertEqual(len(self.requests), 1)

    def test_incomplete_example_is_safe_to_preview_but_not_submit(self):
        self.payload = json.loads((ROOT / 'docs/oshwa-application.example.json').read_text())
        result, stdout, stderr = self.run_cli([str(self.payload_file)])
        self.assertEqual(result, 0, stderr)
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertEqual(self.requests, [])

    def test_signup_uses_names_and_email_without_bearer_auth_and_saves_private_token(self):
        self.response = b'{"token": "fresh-private-token"}'
        token_file = Path(self.temp.name) / 'private/token'
        result, stdout, stderr = self.run_cli([
            '--signup', '--first-name', 'Test', '--last-name', 'Applicant',
            '--email', 'test@example.com', '--token-file', str(token_file),
        ])
        self.assertEqual(result, 0, stderr)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][:3], ('POST', '/users/signup', None))
        self.assertEqual(json.loads(self.requests[0][3]),
                         {'firstName': 'Test', 'lastName': 'Applicant', 'email': 'test@example.com'})
        self.assertEqual(token_file.read_text().strip(), 'fresh-private-token')
        self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('fresh-private-token', stdout + stderr)

    def test_signup_never_overwrites_an_existing_token_or_registers_again(self):
        token_file = Path(self.temp.name) / 'token'
        token_file.write_text('existing token')
        result, stdout, stderr = self.run_cli([
            '--signup', '--first-name', 'Test', '--last-name', 'Applicant',
            '--email', 'test@example.com', '--token-file', str(token_file),
        ])
        self.assertNotEqual(result, 0)
        self.assertEqual(token_file.read_text(), 'existing token')
        self.assertEqual(self.requests, [])

    def test_signup_requires_all_identity_fields_before_any_request(self):
        result, stdout, stderr = self.run_cli([
            '--signup', '--first-name', 'Test', '--email', 'test@example.com',
            '--token-file', str(Path(self.temp.name) / 'token'),
        ])
        self.assertNotEqual(result, 0)
        self.assertEqual(self.requests, [])

    def test_options_can_use_saved_token_without_an_environment_token(self):
        token_file = Path(self.temp.name) / 'token'
        token_file.write_text('saved-token\n')
        self.response = b'{"hardwareLicenseOptions": ["CERN"]}'
        result, stdout, stderr = self.run_cli(['--options', '--token-file', str(token_file)], token='')
        self.assertEqual(result, 0, stderr)
        self.assertEqual(self.requests[0][2], 'Bearer saved-token')

    def test_signup_error_does_not_leave_a_token_file_or_retry(self):
        self.status, self.response = 422, b'{"error": "Email already registered"}'
        token_file = Path(self.temp.name) / 'token'
        result, stdout, stderr = self.run_cli([
            '--signup', '--first-name', 'Test', '--last-name', 'Applicant',
            '--email', 'test@example.com', '--token-file', str(token_file),
        ])
        self.assertNotEqual(result, 0)
        self.assertFalse(token_file.exists())
        self.assertEqual(len(self.requests), 1)

    def test_signup_checks_token_destination_before_registering(self):
        token_file = Path(self.temp.name) / 'token'
        with patch.object(self.module.os, 'open', side_effect=PermissionError('unwritable token destination')):
            result, stdout, stderr = self.run_cli([
                '--signup', '--first-name', 'Test', '--last-name', 'Applicant',
                '--email', 'test@example.com', '--token-file', str(token_file),
            ])
        self.assertNotEqual(result, 0)
        self.assertEqual(self.requests, [])
        self.assertFalse(token_file.exists())

    def test_signup_write_failure_removes_partial_token_and_explains_recovery(self):
        self.response = b'{"token": "fresh-private-token"}'
        token_file = Path(self.temp.name) / 'token'
        real_fdopen = self.module.os.fdopen

        @contextlib.contextmanager
        def failing_writer(fd, mode):
            with real_fdopen(fd, mode) as saved:
                saved.write('partial')
                raise OSError('token write failed')
                yield saved

        with patch.object(self.module.os, 'fdopen', side_effect=failing_writer):
            result, stdout, stderr = self.run_cli([
                '--signup', '--first-name', 'Test', '--last-name', 'Applicant',
                '--email', 'test@example.com', '--token-file', str(token_file),
            ])
        self.assertNotEqual(result, 0)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(token_file.exists())
        self.assertIn('recover', stderr.lower())
        self.assertNotIn('fresh-private-token', stdout + stderr)

    def test_truncated_post_response_reports_unknown_outcome_without_retry(self):
        self.truncated = True
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('before retrying', stderr)
        self.assertEqual(len(self.requests), 1)

    def test_invalid_utf8_post_response_reports_unknown_outcome_without_retry(self):
        self.response = b'\xff'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('before retrying', stderr)
        self.assertEqual(len(self.requests), 1)

    def test_server_error_after_post_warns_about_possible_submission(self):
        self.status, self.response = 500, b'Server error'
        result, stdout, stderr = self.run_cli([str(self.payload_file), '--submit'])
        self.assertNotEqual(result, 0)
        self.assertIn('before retrying', stderr)
        self.assertEqual(len(self.requests), 1)
