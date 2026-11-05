"""Dashboard integration tests; the OpenAI transport is simulated."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from flowsense.agent import ask
from flowsense.generator import generate_data, save_to_sqlite

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError as error:
    if error.name != "streamlit":
        raise
    AppTest = None


@unittest.skipIf(AppTest is None, "Install Streamlit to run dashboard tests")
class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = cls.enterClassContext(tempfile.TemporaryDirectory())
        cls.app = Path(directory) / "streamlit_demo.py"
        shutil.copyfile(Path(__file__).resolve().parents[1] / cls.app.name, cls.app)
        save_to_sqlite(generate_data(), cls.app.parent / "data" / "flowsense.sqlite")

    def test_charts_and_filters_without_api_credentials(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""}):
            app = AppTest.from_file(str(self.app)).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button[0].disabled)
            self.assertEqual([metric.value for metric in app.metric], [
                "-61.3 million USD equivalent", "+0.53", "+1.22 index points",
            ])
            self.assertEqual(len(app.get("vega_lite_chart")), 2)
            app.selectbox[0].set_value("Europe").run()
            self.assertFalse(app.exception)
            self.assertTrue(app.metric[0].value.startswith("-137.5"))

    def test_fresh_checkout_generates_database(self):
        with tempfile.TemporaryDirectory() as directory:
            app_path = Path(directory) / self.app.name
            shutil.copyfile(self.app, app_path)
            database = app_path.parent / "data" / "flowsense.sqlite"
            with patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""}):
                app = AppTest.from_file(str(app_path)).run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertTrue(database.is_file())
                self.assertEqual(app.metric[1].value, "+0.53")
                modified_at = database.stat().st_mtime_ns
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(database.stat().st_mtime_ns, modified_at)

    def test_question_runs_real_tool_loop_and_retains_evidence(self):
        arguments = {"region": "US", "asset_class": "equities",
                     "start_date": None, "end_date": None, "limit": 1}
        answer = {"observations": [{"text": "Net flow was negative.", "evidence_ids": ["E1"]}],
                  "hypotheses": [], "limitations": ["Synthetic data."]}
        responses = iter([
            {"status": "completed", "output": [{"type": "function_call", "name": "get_metrics",
                                               "call_id": "call_1", "arguments": json.dumps(arguments)}]},
            {"status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(answer)}]}]},
        ])

        def simulated_ask(question, tools, model):
            return ask(question, tools, model, transport=lambda _: next(responses))

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test"}), patch(
            "flowsense.agent.ask", side_effect=simulated_ask
        ) as ask_mock:
            app = AppTest.from_file(str(self.app)).run()
            app.text_area[0].set_value("What stands out in the latest US equity flows?")
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertIn("• Net flow was negative. [E1]", [item.value for item in app.text])
            fields = app.dataframe[0].value.set_index("Field")["Value"]
            self.assertEqual(fields["arguments.start_date"], "null")
            self.assertEqual(fields["result.rows[0].net_flow"], "-61.3197474421")
            app.selectbox[0].set_value("Europe").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe), 1)
            ask_mock.assert_called_once()
