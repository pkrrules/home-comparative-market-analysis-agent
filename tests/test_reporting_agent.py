import json
import unittest
from unittest.mock import Mock, patch

import _pathfix  # noqa: F401
from reporting_agent import OpenAIReportingAgent, verified_reporting_facts
from test_report import ANALYSIS_DATE, STEP, make_property
from comparable_engine import evaluate_candidates


def scenario():
    subject = make_property("SUBJ")
    result = evaluate_candidates(
        subject,
        [make_property(f"C{i}", close_price=260_000 + i * 10_000) for i in range(3)],
        STEP,
        ANALYSIS_DATE,
    )
    return subject, result


class TestOpenAIReportingAgent(unittest.TestCase):
    def test_missing_key_uses_deterministic_fallback_without_network(self):
        subject, result = scenario()
        with patch.dict("reporting_agent.os.environ", {}, clear=True), patch("reporting_agent.requests.post") as post:
            outcome = OpenAIReportingAgent().generate(subject, result)
        self.assertIsNone(outcome.narrative)
        self.assertIn("OPENAI_API_KEY", outcome.status)
        post.assert_not_called()

    def test_verified_payload_omits_listing_ids_and_addresses(self):
        subject, result = scenario()
        encoded = json.dumps(verified_reporting_facts(subject, result))
        self.assertNotIn("SUBJ", encoded)
        self.assertNotIn("C0", encoded)
        self.assertNotIn("Test St", encoded)

    @patch("reporting_agent.requests.post")
    def test_valid_structured_narrative_is_returned(self, post):
        subject, result = scenario()
        response = Mock()
        response.ok = True
        response.json.return_value = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({
            "comparison_summary": "The approved sales form a coherent comparison set.",
            "strengths": "The strongest evidence is similar in physical characteristics.",
            "limitations": "Some property differences remain and sample data limits interpretation.",
            "interpretation": "The evidence supports the deterministic indication with appropriate caution.",
        })}]}]}
        post.return_value = response
        outcome = OpenAIReportingAgent(api_key="test-key").generate(subject, result)
        self.assertEqual(outcome.status, "AI narrative generated")
        self.assertIn("AI-assisted evidence commentary", outcome.narrative)
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")

    @patch("reporting_agent.requests.post")
    def test_numeric_model_output_is_rejected(self, post):
        subject, result = scenario()
        response = Mock()
        response.ok = True
        response.json.return_value = {"output_text": json.dumps({
            "comparison_summary": "The estimate is $999999.",
            "strengths": "Strong evidence.",
            "limitations": "Sample limitations apply.",
            "interpretation": "Use caution.",
        })}
        post.return_value = response
        outcome = OpenAIReportingAgent(api_key="test-key").generate(subject, result)
        self.assertIsNone(outcome.narrative)
        self.assertIn("fallback", outcome.status)


if __name__ == "__main__":
    unittest.main()
