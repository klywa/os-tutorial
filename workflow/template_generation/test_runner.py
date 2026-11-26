import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from workflow.template_generation import run


class RunnerTest(unittest.TestCase):
    """Transport doubles exercise the checkpoint and publication boundaries offline."""

    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.directory = self.base / "run"
        self.source = self.base / "稿.txt"
        self.source.write_text("购买机会由场上搭档决定。", encoding="utf-8")
        self.output = self.base / "导出" / "话术.json"
        self.sidecar = self.output.with_name("话术-detail.json")
        self.calls = []
        self.bad = set()
        self.points = [
            {"id": pid, "source_refs": [{"quote": "场上搭档", "location": "第一句"}],
             "related_ids": [], "knowledge": pid}
            for pid in ("甲", "乙")]
        self.barrier = threading.Barrier(2, timeout=10)
        replacements = (("prepare", self.prepare), ("validate", self.validate), ("assemble", self.assemble))
        for key, function in replacements:
            mock = patch.object(run.nodes, key, function)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.object(run.providers, "generate", self.generate)
        mock.start()
        self.addCleanup(mock.stop)

    def invoke(self, command, *args, expected=0):
        if command == "start":
            args = (self.source, "--output", self.output, "--model", "offline", *args)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = run.main([command, "--run-dir", str(self.directory), *map(str, args)])
        self.assertEqual(expected, code, buf.getvalue())
        return buf.getvalue()

    @staticmethod
    def prepare(stage, source, point, previous):
        return json.dumps({"stage": stage, "point": point, "source": source, "previous": previous}, ensure_ascii=False)

    def generate(self, provider, model, prompt):
        args = json.JSONDecoder().raw_decode(prompt)[0]
        stage, point = args["stage"], args["point"]
        pid = point["id"] if point else None
        pair = (stage, pid)
        self.calls.append(pair)
        if pair in self.bad:
            return "bad JSON"
        if stage == "identify":
            data = {"points": self.points}
        elif stage == "enrich":
            if self.calls.count(pair) == 1:
                self.barrier.wait()
            data = {"point_id": pid, "scope": "限定阵容"}
        elif stage == "events":
            data = {"point_id": pid, "events": [{"id": "buy"}]}
        elif stage == "conditions":
            data = {"point_id": pid, "conditions": [{"id": "partner", "event_id": "buy",
                                                     "scope": args["previous"]["enrich"]["scope"]}]}
        else:
            data = {"point_id": pid, "text": args["previous"]["conditions"]["conditions"][0]["scope"]}
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def validate(stage, result, previous):
        if stage == "enrich" and result.get("scope") not in ("限定阵容", "已上场搭档"):
            raise ValueError("scope 无效")
        return result

    @staticmethod
    def assemble(branches):
        groups, links = [], {}
        for pid, branch in branches.items():
            gid, sid = "组" + pid, "句" + pid
            groups.append({"id": gid, "syntax_version": "0.4", "utterances": [
                {"id": sid, "text": branch["phrases"]["text"]}]})
            links[gid] = {sid: {"point_id": pid, "event_id": "buy", "condition_id": "partner"}}
        return {"schema_version": 3, "groups": groups}, links

    def revise(self, stage, data, pid=None, expected=0):
        path = self.base / "修订.json"
        run.save(path, data)
        args = ["--stage", stage, "--file", path]
        if pid:
            args.extend(["--point", pid])
        return self.invoke("revise", *args, expected=expected)

    def test_barrier_revisions_and_complete_trace(self):
        self.invoke("start", "--pause-after", "enrich")
        self.assertCountEqual(self.calls, [("identify", None), ("enrich", "甲"), ("enrich", "乙")])
        self.assertFalse(self.output.exists())
        invalid = self.revise("enrich", {"scope": "缺证据"}, "甲", expected=1)
        self.assertIn("scope 无效", invalid)
        self.revise("enrich", {"point_id": "甲", "scope": "已上场搭档"}, "甲")
        self.invoke("resume")
        detail = run.read(self.sidecar)
        self.assertEqual(detail["library_sha256"], run.digest(self.output.read_bytes()))
        sentence = detail["groups"]["组甲"]["sentences"]["句甲"]
        self.assertEqual(sentence["text"], "已上场搭档")
        self.assertEqual([detail["nodes"][k]["stage"] for k in sentence["node_ids"]], list(run.STAGES))
        node = detail["nodes"]["enrich:甲"]
        self.assertEqual(node["selected_version"], "r2")
        self.assertEqual(json.loads(node["attempts"][0]["raw"])["scope"], "限定阵容")
        self.assertIn("scope", node["revisions"][0]["error"])
        downstream = detail["nodes"]["events:甲"]
        self.assertIn("已上场搭档", downstream["attempts"][0]["prompt"])
        self.assertEqual(downstream["input"]["versions"]["enrich:甲"], "r2")
        self.assertEqual(detail["groups"]["组乙"]["sentences"]["句乙"]["text"], "限定阵容")
        self.assertEqual(len(self.calls), 9)
        self.invoke("resume")
        self.assertEqual(len(self.calls), 9)

    def test_bad_model_output_retry_keeps_sibling_and_attempt(self):
        self.bad.add(("conditions", "甲"))
        error = self.invoke("start", expected=1)
        self.assertIn("conditions:甲", error)
        self.assertFalse(self.output.exists())
        self.bad.clear()
        self.invoke("resume")
        self.assertEqual(self.calls.count(("conditions", "乙")), 1)
        attempts = run.read(self.sidecar)["nodes"]["conditions:甲"]["attempts"]
        self.assertEqual([a["id"] for a in attempts], ["a1", "a2"])
        self.assertEqual(attempts[0]["raw"], "bad JSON")
        self.assertTrue(attempts[0]["error"])
        self.assertEqual(attempts[1]["repairs"], "a1")
        feedback = json.loads(attempts[1]["prompt"].splitlines()[-1])
        self.assertEqual(feedback, {"error": attempts[0]["error"], "raw": attempts[0]["raw"]})

    def test_failed_run_retains_pending_review_barrier_on_resume(self):
        self.bad.add(("identify", None))
        self.invoke("start", "--pause-after", "enrich", expected=1)
        self.bad.clear()
        self.invoke("resume")
        manifest = run.read(self.directory / "run.json")
        self.assertEqual(manifest["status"], "paused")
        self.assertEqual(manifest["checkpoint"]["stage"], "enrich")
        self.assertNotIn(("events", "甲"), self.calls)
        self.assertFalse(self.output.exists())
        self.invoke("resume")
        self.assertTrue(self.output.exists())

    def test_identify_revision_invalidates_only_changed_branch(self):
        self.invoke("start", "--pause-after", "conditions")
        self.points[0]["knowledge"] = "修订知识"
        self.revise("identify", {"points": self.points})
        self.assertIn("识别结果已修订", self.revise("conditions", {}, "甲", expected=1))
        self.invoke("resume")
        for stage in ("enrich", "events", "conditions"):
            self.assertEqual(self.calls.count((stage, "甲")), 2)
            self.assertEqual(self.calls.count((stage, "乙")), 1)
        detail = run.read(self.sidecar)
        self.assertEqual(detail["groups"]["组甲"]["sentences"]["句甲"]["node_versions"]["identify"], "r1")
        self.assertEqual(detail["groups"]["组乙"]["sentences"]["句乙"]["node_versions"]["identify"], "a1")

    def test_provider_reply_wrappers_do_not_hide_prose_or_extra_objects(self):
        wrapped = '</think>\n```json\n{"point_id":"甲"}\n```'
        self.assertEqual(run.parse_reply(wrapped), {"point_id": "甲"})
        for invalid in [wrapped + "\n更多", "{} {}", "说明\n{}", '{"n":NaN}', '{"n":1e999}']:
            with self.assertRaises(ValueError):
                run.parse_reply(invalid)

    def test_resource_change_rechecks_selected_outputs(self):
        self.invoke("start", "--pause-after", "conditions")
        with patch.object(run, "resource_versions", return_value={"prompts/identify.md": "changed"}):
            self.invoke("resume")
        self.assertEqual(self.calls.count(("identify", None)), 2)
        detail = run.read(self.sidecar)
        self.assertEqual(len(detail["resource_versions"]), 2)
        identify = detail["nodes"]["identify"]
        self.assertEqual(identify["selected_version"], "a2")
        self.assertNotEqual(*(a["resource_version"] for a in identify["attempts"]))

    def test_publication_keeps_existing_pair(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"existing library")
        self.sidecar.write_bytes(b"existing detail")
        self.invoke("start", expected=1)
        self.assertEqual(self.output.read_bytes(), b"existing library")
        self.assertEqual(self.sidecar.read_bytes(), b"existing detail")

    def test_interrupted_pair_publication_recovers_without_more_model_calls(self):
        write = run.write_bytes

        def interrupt(path, data, *, exclusive=False):
            if path == self.output and exclusive:
                raise OSError("模拟发布中断")
            write(path, data, exclusive=exclusive)

        with patch.object(run, "write_bytes", interrupt):
            self.invoke("start", expected=1)
        self.assertTrue(self.sidecar.exists())
        self.assertFalse(self.output.exists())
        calls = list(self.calls)
        with patch.object(run, "resource_versions", return_value={"prompts/identify.md": "changed"}):
            self.invoke("resume")
        self.assertEqual(self.calls, calls)
        self.assertEqual(run.read(self.sidecar)["library_sha256"], run.digest(self.output.read_bytes()))


if __name__ == "__main__":
    unittest.main()
