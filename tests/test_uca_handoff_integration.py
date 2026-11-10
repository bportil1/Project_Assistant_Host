"""UCA-10 explicit handoff checks, independent of Flask."""
import unittest
from pah.contracts.uca_coordination import AnalysisHandoff, HandoffError, inspect_handoff
from pah.contracts.artifacts import ArtifactRef
from pah.jobs import JobMonitorAggregator
from pah_jobs import JobRegistry

class HandoffIntegration(unittest.TestCase):
    def setUp(self):
        self.registry=JobRegistry('code_analyzer')
        self.monitor=JobMonitorAggregator()
        self.monitor.attach(self.registry.reader())
        self.job=self.registry.start('logical', 'test job')
        self.sha='1'*64
        self.handoff=AnalysisHandoff('project','repository','code_analyzer',self.sha,self.job,'artifact')
    def inspect(self,artifact=None):
        return inspect_handoff(self.handoff,project_id='project',repository_id='repository',readers=self.monitor.readers_snapshot(),artifact=artifact)
    def test_real_reader_observation_is_not_artifact_validation(self):
        item=self.inspect()
        self.assertEqual(item['job']['verification'],'observed')
        self.assertEqual(item['artifact']['verification'],'unavailable')
    def test_producer_issued_artifact_with_matching_provenance(self):
        artifact=ArtifactRef(artifact_id='artifact',kind='structure',producer_module='code_analyzer',project_id='project',validation_state='valid',provenance={'source_sha256':self.sha})
        self.assertEqual(self.inspect(artifact)['artifact']['verification'],'producer_validated')
    def test_missing_provenance_is_not_verified(self):
        artifact=ArtifactRef(artifact_id='artifact',kind='structure',producer_module='code_analyzer',project_id='project',validation_state='valid')
        self.assertEqual(self.inspect(artifact)['artifact']['verification'],'source_unverified')
    def test_project_mismatch_fails_closed(self):
        with self.assertRaises(HandoffError):
            inspect_handoff(self.handoff,project_id='different',repository_id='repository',readers={})
    def test_detached_reader_is_unavailable(self):
        self.monitor.detach('code_analyzer')
        self.assertEqual(self.inspect()['job']['verification'],'unavailable')
