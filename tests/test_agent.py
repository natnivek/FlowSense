import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from flowsense.agent import AnalyticsTools, ask, render_answer, request_response
from flowsense.generator import generate_data, save_to_sqlite


def query(**updates):
    return {"region": "US", "asset_class": "equities", "start_date": None,
            "end_date": None, "limit": 1, **updates}


def response(*items, status="completed"):
    return {"status": status, "output": list(items)}


def call(name, args, call_id="call_1"):
    return {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": call_id}


def final(ids=None, observations=True):
    answer = {"observations": [{"text": "Latest equity flow is above its recent baseline.",
                                "evidence_ids": ids or ["E1"]}] if observations else [],
              "hypotheses": [], "limitations": ["Synthetic flows do not establish investor intent."]}
    return response({"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]})


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "flows.sqlite"
        save_to_sqlite(generate_data(), cls.path)
        cls.tools = AnalyticsTools(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_tools_match_engine_and_default_latest(self):
        original = self.path.read_bytes()
        result = self.tools.execute("get_metrics", query())
        row = result["rows"][0]
        expected = self.tools.metrics.query("asset_class == 'equities' and region == 'US'").iloc[-1]
        self.assertEqual(row["date"], "2025-12-31")
        self.assertAlmostEqual(row["flow_zscore"], expected.flow_zscore, places=9)
        self.assertEqual(result["window"], 20)
        self.assertNotIn("regime", row)
        self.assertEqual(original, self.path.read_bytes())

    def test_range_truncation_nulls_and_empty_results(self):
        result = self.tools.execute("get_metrics", query(start_date="2024-01-01", end_date="2024-01-05", limit=2))
        self.assertEqual(result["matching_rows"], 5)
        self.assertTrue(result["truncated"])
        self.assertIsNone(result["rows"][0]["flow_zscore"])
        json.dumps(result, allow_nan=False)
        empty = self.tools.execute("get_metrics", query(end_date="2026-01-01"))
        self.assertEqual(empty["rows"], [])

    def test_pair_filter_and_coverage(self):
        result = self.tools.execute("get_divergences", query(limit=60))
        self.assertEqual(result["returned_rows"], 2)
        for row in result["rows"]:
            self.assertIn("equities", [row["asset_a"], row["asset_b"]])
            self.assertAlmostEqual(row["zscore_spread"], row["zscore_a"] - row["zscore_b"], places=8)
        self.assertTrue(self.tools.execute("describe_dataset", {})["synthetic"])

    def test_rejects_untrusted_tool_requests(self):
        for name, arguments in [("run_sql", {}), ("get_metrics", query(limit=1000)),
                                ("get_metrics", query(region="Mars")),
                                ("get_metrics", query(start_date="2025-12-31", end_date="2024-01-01")),
                                ("get_metrics", query(end_date="not-a-date")),
                                ("get_metrics", query(end_date="2025-1-1")),
                                ("get_metrics", {**query(), "sql": "DROP TABLE flows"})]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ValueError):
                self.tools.execute(name, arguments)

    def test_mocked_roundtrip_trace_and_rendering(self):
        requests = []
        replies = iter([response(call("get_metrics", query())), final()])
        def transport(payload):
            requests.append(json.loads(json.dumps(payload)))
            return next(replies)
        result = ask("How are latest US equity flows?", self.tools, "test-model", transport)
        self.assertEqual(len(requests), 2)
        self.assertFalse(requests[0]["store"])
        self.assertEqual(requests[1]["input"][-1]["type"], "function_call_output")
        self.assertEqual(result["evidence"][0]["evidence_id"], "E1")
        rendered = render_answer(result)
        self.assertIn("[E1]", rendered)
        self.assertIn("2025-12-31", rendered)
        self.assertIn("Hypotheses (unverified)", rendered)

    def test_fabricated_citation_and_unfinished_response_rejected(self):
        for reply in [final(["invented"]), response(status="incomplete"), response()]:
            with self.assertRaises(RuntimeError):
                ask("question", self.tools, "test-model", lambda _: reply)

    def test_invalid_tool_can_recover_without_evidence(self):
        replies = iter([response(call("execute_python", {})), final(observations=False)])
        result = ask("Run code", self.tools, "test-model", lambda _: next(replies))
        self.assertEqual(result["evidence"], [])
        self.assertIn("No supported data observation", render_answer(result))

    def test_round_limit_and_missing_configuration(self):
        with self.assertRaises(RuntimeError):
            ask("question", self.tools, "test-model", lambda _: response(call("describe_dataset", {})), max_rounds=2)
        with self.assertRaises(ValueError):
            ask("", self.tools, "test-model")
        with self.assertRaises(ValueError):
            ask("question", self.tools, "")
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
            request_response({})

    def test_http_payload_and_credentials_not_exposed(self):
        from unittest.mock import MagicMock
        reply = MagicMock()
        reply.__enter__.return_value.read.return_value = b'{"status":"completed","output":[]}'
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret"}), patch(
            "urllib.request.urlopen", return_value=reply
        ) as send:
            self.assertEqual(request_response({"store": False})["status"], "completed")
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertEqual(json.loads(request.data), {"store": False})
        error = urllib.error.HTTPError("url", 401, "test-secret", {}, None)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-secret"}), patch(
            "urllib.request.urlopen", side_effect=error
        ), self.assertRaises(RuntimeError) as caught:
            request_response({})
        self.assertNotIn("test-secret", str(caught.exception))

    def test_tool_count_is_bounded(self):
        reply = response(*[call("describe_dataset", {}, str(i)) for i in range(13)])
        with self.assertRaisesRegex(RuntimeError, "count limit"):
            ask("question", self.tools, "test-model", lambda _: reply)
