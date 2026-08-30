"""
Streamlit UI test, using Streamlit's own scripted-testing framework
(AppTest) instead of a browser — drives real widget interactions
(button clicks, selectbox changes) and inspects the rendered output,
exercising the same graph.invoke/Command(resume=...) calls a real user's
clicks would trigger. Runs entirely against the frozen fixture data
source (default), no network.
"""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


class TestAppLoadsCleanly(unittest.TestCase):
    def test_loads_without_exception(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        self.assertFalse(at.exception)

    def test_default_data_source_is_fixture(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        self.assertEqual(at.sidebar.radio[0].value, "Frozen fixture sample (recommended — no API quota used)")

    def test_demo_subject_picker_populated(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        self.assertGreaterEqual(len(at.sidebar.selectbox[0].options), 6)


class TestApproveToCompletion(unittest.TestCase):
    def test_full_flow_reaches_a_checked_briefing(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        run_button = [b for b in at.button if b.label == "Run analysis"][0]
        run_button.click().run()
        self.assertFalse(at.exception)

        # Click "approve" for as many expansion rounds as the search needs
        # (bounded by the number of expansion steps, so this can't loop forever).
        for _ in range(4):
            approve = [b for b in at.button if b.label.startswith("✅")]
            if not approve:
                break
            approve[0].click().run()
            self.assertFalse(at.exception)

        # Should have reached a final state with no more approval buttons pending
        self.assertFalse([b for b in at.button if b.label.startswith("✅")])
        metrics = {m.label: m.value for m in at.metric}
        self.assertIn("Comparables selected", metrics)

        full_text = "\n".join(m.value for m in at.markdown)
        self.assertIn("Comparable Home Analysis", full_text)

        expander_labels = [e.label for e in at.expander]
        self.assertTrue(any("Report self-check" in label for label in expander_labels))
        self_check_expander = next(e for e in at.expander if "Report self-check" in e.label)
        self.assertTrue(all(m.value.startswith("✅") for m in self_check_expander.markdown))


class TestDeclinePath(unittest.TestCase):
    def test_declining_immediately_still_produces_a_briefing(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        [b for b in at.button if b.label == "Run analysis"][0].click().run()
        decline = [b for b in at.button if b.label.startswith("🛑")]
        self.assertTrue(decline)
        decline[0].click().run()
        self.assertFalse(at.exception)
        metrics = {m.label: m.value for m in at.metric}
        self.assertEqual(metrics["Sufficient (≥3 found)"], "No")


class TestStartOver(unittest.TestCase):
    def test_start_over_clears_state(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        [b for b in at.button if b.label == "Run analysis"][0].click().run()
        self.assertTrue(at.warning)  # an approval prompt should be showing

        [b for b in at.button if b.label == "Start over"][0].click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.warning)
        self.assertFalse(at.metric)


class TestUnknownSubject(unittest.TestCase):
    def test_unknown_custom_mls_number_shows_error(self):
        at = AppTest.from_file(APP_PATH, default_timeout=60).run()
        at.sidebar.selectbox[0].set_value("Custom MLS number…").run()
        at.sidebar.text_input[0].set_value("NO-SUCH-ID").run()
        [b for b in at.button if b.label == "Run analysis"][0].click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("No subject property could be resolved" in e.value for e in at.error))


if __name__ == "__main__":
    unittest.main()
