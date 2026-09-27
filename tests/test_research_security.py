import pytest

from core.lab_v1.research_skill_autopilot import ResearchPipelineError, _assert_public_url
from core.lab_v1.research_skill_autopilot import AutonomousResearchSkillPipeline


@pytest.mark.parametrize("url", [
    "http://localhost/private",
    "http://127.0.0.1:8080/metadata",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.4/internal",
    "file:///C:/Windows/System32/config/SAM",
])
def test_research_rejects_local_private_or_non_http_targets(url: str):
    with pytest.raises(ResearchPipelineError):
        _assert_public_url(url)


def test_research_rejects_invalid_host():
    with pytest.raises(ResearchPipelineError):
        _assert_public_url("https://host-that-does-not-exist.invalid/source")


def test_skill_operations_reject_path_traversal(tmp_path):
    pipeline = AutonomousResearchSkillPipeline(tmp_path / "skills", fetcher=lambda _url: b"safe")
    with pytest.raises(ResearchPipelineError):
        pipeline.record_test("../outside", "1.0.0", "smoke", passed=True, summary="x")
    with pytest.raises(ResearchPipelineError):
        pipeline.activate("safe", "../../outside", owner_approved=True)
    with pytest.raises(ResearchPipelineError):
        pipeline.rollback("safe", to_version="../outside")
