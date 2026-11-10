"""UCA-10 owner and provenance boundary tests; no web app needed."""
import unittest
from pah.contracts.uca_coordination import AnalysisHandoff, HandoffError, inspect_handoff
from pah.contracts.artifacts import ArtifactRef
from pah_jobs import JobRegistry

SHA = 'a' * 64


def ref(**updates):
    params = dict(artifact_id='artifact-1', kind='structure', producer_module='code_analyzer',
                  project_id='project-a', validation_state='valid', provenance={'source_sha256': SHA})
    params.update(updates)
    return ArtifactRef(**params)


class TestHandoff(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry('code_analyzer')
        self.id = self.registry.start('logical', 'fixture')
        self.handoff = AnalysisHandoff('project-a', 'repo-1', 'code_analyzer', SHA,
                                        job_id=self.id, artifact_id='artifact-1')

    def inspect(self, **kwargs):
        return inspect_handoff(self.handoff, project_id='project-a', repository_id='repo-1',
                               readers={'code_analyzer': self.registry.reader()}, **kwargs)

    def test_observes_producer_owned_job_and_verified_artifact(self):
        result = self.inspect(artifact=ref())
        self.assertEqual(result['job']['verification'], 'observed')
        self.assertEqual(result['artifact']['verification'], 'producer_validated')

    def test_no_job_reader_does_not_claim_completion(self):
        result = inspect_handoff(self.handoff, project_id='project-a', repository_id='repo-1',
                                 readers={}, artifact=ref())
        self.assertEqual(result['job']['verification'], 'unavailable')

    def test_cross_project_rejected(self):
        with self.assertRaises(HandoffError):
            inspect_handoff(self.handoff, project_id='project-b', repository_id='repo-1', readers={})

    def test_mismatched_artifact_owner_rejected(self):
        with self.assertRaises(HandoffError):
            self.inspect(artifact=ref(producer_module='pypique'))

    def test_missing_and_wrong_source_provenance_not_validated(self):
        self.assertEqual(self.inspect(artifact=ref(provenance={}))['artifact']['verification'], 'source_unverified')
        self.assertEqual(self.inspect(artifact=ref(provenance={'source_sha256': 'b'*64}))['artifact']['verification'], 'source_mismatch')

    def test_unknown_validation_state_not_upgraded(self):
        self.assertEqual(self.inspect(artifact=ref(validation_state='unknown'))['artifact']['verification'], 'unknown')

    def test_require_explicit_identity(self):
        with self.assertRaises(HandoffError):
            AnalysisHandoff('project-a','repo-1','code_analyzer', SHA)
        with self.assertRaises(HandoffError):
            AnalysisHandoff('project-a','repo-1','code_analyzer','wrong',job_id='job')

    def test_missing_artifact_remains_unavailable(self):
        self.assertEqual(self.inspect()['artifact']['verification'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
