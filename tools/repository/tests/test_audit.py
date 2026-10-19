import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('repo_audit', Path(__file__).parents[1] / 'audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_secret_value_is_not_returned(self):
        value = 'fabricated-' + 'credential-123'
        result = audit.secret_findings('example.py', 'password=' + repr(value))
        self.assertEqual(result[0]['rule'], 'literal-credential')
        self.assertNotIn(value, str(result))

    def test_environment_reference_is_not_literal(self):
        self.assertEqual([], audit.secret_findings('x.py', "password=os.environ['WT_PI_PASSWORD']"))

    def test_key_detection(self):
        header = '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----'
        self.assertEqual('private-key', audit.secret_findings('key', header)[0]['rule'])

    def test_link_normalization(self):
        self.assertEqual('Docs/a.md', audit.normalize_link('Docs/tests/x.md', '../a.md#test'))
        self.assertIsNone(audit.normalize_link('Docs/a.md', 'https://example.com'))
        self.assertIsNone(audit.normalize_link('Docs/a.md', '#heading'))

    def test_case_sensitive_presence(self):
        files = {'Docs/README.md', 'Electronics/lib/a.kicad_mod'}
        self.assertTrue(audit.is_present('Docs', files))
        self.assertFalse(audit.is_present('docs/README.md', files))
        self.assertTrue(audit.is_present('Electronics/lib', files))

    def test_personal_paths_are_redacted(self):
        path = '/'.join(['C:', 'Users', 'private-example', 'file.txt'])
        findings = audit.public_findings('example.md', path)
        self.assertEqual(findings[0]['rule'], 'personal-windows-path')
        self.assertNotIn(path, str(findings))
        unix = '/'.join(['', 'home', 'private-example', 'file'])
        self.assertEqual('personal-home-path', audit.public_findings('x', unix)[0]['rule'])

    def test_generic_placeholders_and_vendor_runtime_are_not_personal(self):
        text = '%LOCALAPPDATA%/Programs /home/' + 'ofuser/OpenFOAM'
        self.assertEqual([], audit.public_findings('x', text))

    def test_public_cad_policy(self):
        policy = json.loads((Path(__file__).parents[1] / 'publication_policy.json').read_text())
        self.assertEqual(len(policy['allowed_cad']), 8)
        for name in policy['allowed_cad']:
            self.assertIsNone(audit.public_path_error(name, policy))
        for name in ['download.step', 'bundle.zip::windtunnel.stl', 'body.f3d']:
            self.assertEqual(audit.public_path_error(name, policy), 'unreviewed-cad')
        self.assertEqual(audit.public_path_error(policy['excluded_files'][0], policy),
                         'excluded-publication-file')
        self.assertEqual(audit.public_path_error('external/vendor/readme.md', policy),
                         'excluded-publication-prefix')
        self.assertIsNone(audit.public_path_error('Docs/tests/independent-report.md', policy))


if __name__ == '__main__':
    unittest.main()
