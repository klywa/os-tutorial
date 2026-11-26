"""Durable command-line runner for the seven template generation stages."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from uuid import uuid4

if __package__:
    from . import nodes, providers
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from workflow.template_generation import nodes, providers


BRANCH_STAGES = ("enrich", "events", "conditions", "phrases")
STAGES = ("identify", "split", *BRANCH_STAGES, "assemble")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"JSON 数值无效：{value}")
    return number


def parse_json(raw):
    return json.loads(raw, parse_float=parse_number, parse_constant=parse_number)


def parse_reply(raw):
    value = raw.strip().removeprefix("</think>").strip()
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", value, re.IGNORECASE | re.DOTALL)
    return parse_json(fenced.group(1) if fenced else value)


def write_bytes(path, data, *, exclusive=False):
    """Install a fully written file. Publication never replaces an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
        tmp = Path(stream.name)
    try:
        with tmp.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save(path, value):
    write_bytes(path, encoded(value))


@contextmanager
def run_lock(directory):
    # OS releases this lock on process exit, including an interrupted provider call.
    with (directory / ".lock").open("a+b") as lock:
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError(f"该运行正由其他进程使用：{directory}") from error
        yield


def node_key(stage, point_id=None):
    return f"{stage}:{point_id}" if point_id is not None else stage


def now():
    return datetime.now(timezone.utc).isoformat()


def resource_versions():
    base = Path(__file__).resolve().parent
    return {p.relative_to(base).as_posix(): digest(p.read_bytes())
            for folder in ("prompts", "references", "knowledge")
            for p in sorted((base / folder).rglob("*")) if p.is_file()}


class Run:
    def __init__(self, directory):
        self.directory = directory
        self.manifest = read(directory / "run.json")
        self.source = (directory / "source.txt").read_text(encoding="utf-8")
        if digest(self.source.encode()) != self.manifest["source_sha256"]:
            raise ValueError("运行目录中的原文与初始版本不一致")
        resources = resource_versions()
        self.resource_version = digest(encoded(resources))
        self.generation_version = digest(encoded({k: v for k, v in resources.items() if k != "prompts/repair.md"}))
        self.manifest.setdefault("resource_versions", {})[self.resource_version] = resources

    def status(self, status, **details):
        self.manifest.update(status=status, checkpoint=details)
        save(self.directory / "run.json", self.manifest)

    def node_path(self, stage, point_id):
        if point_id is None:
            return self.directory / "nodes" / f"{stage}.json"
        # Model-generated identifiers never become file names.
        return self.directory / "nodes" / digest(point_id.encode()) / f"{stage}.json"

    def evaluate(self, stage, point_id, inputs, compute=None, upstream_versions=None):
        path = self.node_path(stage, point_id)
        key = node_key(stage, point_id)
        record = read(path) if path.exists() else dict(
            id=key, stage=stage, point_id=point_id, attempts=[], revisions=[])
        signature = digest(encoded([inputs, self.generation_version]))
        same_input = record.get("signature") == signature
        if same_input and record.get("selected_version"):
            return record
        previous = record["attempts"][-1] if same_input and record["attempts"] else {}
        record.update(input=inputs, signature=signature, selected_version=None, output=None)
        attempt = {"id": f"a{len(record['attempts']) + 1}", "started": now(), "resource_version": self.resource_version,
                   "input": inputs, "error": None}
        if upstream_versions:
            attempt["upstream_versions"] = upstream_versions
        record["attempts"].append(attempt)
        save(path, record)
        try:
            if compute:
                output = compute()
                attempt["kind"] = "code"
            else:
                attempt.update(kind="model", provider=self.manifest["provider"], model=self.manifest["model"])
                prompt = nodes.prepare(stage, inputs.get("source", ""), inputs.get("point"), inputs["previous"])
                if previous.get("error") and "raw" in previous:
                    repair = Path(__file__).with_name("prompts") / "repair.md"
                    failure = {"error": previous["error"], "raw": previous["raw"]}
                    prompt += "\n\n" + repair.read_text(encoding="utf-8").strip() + "\n" + json.dumps(failure, ensure_ascii=False)
                    attempt["repairs"] = previous["id"]
                attempt["prompt"] = prompt
                save(path, record)
                raw = providers.generate(attempt["provider"], attempt["model"], prompt)
                attempt["raw"] = raw
                attempt["parsed"] = parse_reply(raw)
                output = nodes.validate(stage, attempt["parsed"], inputs["previous"])
            attempt["output"] = output
            record.update(output=output, selected_version=attempt["id"])
        except Exception as error:
            attempt["error"] = str(error)
            raise ValueError(f"{key} / {attempt['id']}：{error}") from error
        finally:
            attempt["finished"] = now()
            save(path, record)
        return record

    def revise(self, stage, point_id, file):
        if self.manifest["status"] == "complete":
            raise ValueError("已发布的运行已封存，请新建运行")
        if self.manifest.get("publishing") and self.sidecar().is_file():
            if digest(self.sidecar().read_bytes()) == self.manifest["publishing"]:
                raise ValueError("配套文件正在发布，请先 resume 完成本次发布")
        if (stage == "identify") != (point_id is None):
            raise ValueError("识别节点无需 --point，分支节点必须指定 --point")
        path = self.node_path(stage, point_id)
        record = read(path)
        if record["signature"] != digest(encoded([record["input"], self.generation_version])):
            raise ValueError("节点资料已更新，请先恢复运行至该节点再修订")
        if point_id is not None:
            identify = read(self.node_path("identify", None))
            current = {p["id"]: p for p in identify["output"]["points"]}
            enrich = read(self.node_path("enrich", point_id))
            previous = enrich["input"]["previous"]
            if current.get(point_id) != previous["point"] or any(
                    current.get(p["id"]) != p for p in previous["related_points"]):
                raise ValueError("识别结果已修订，请先恢复运行至该节点再修订")
            for earlier in BRANCH_STAGES[:BRANCH_STAGES.index(stage)]:
                ancestor = read(self.node_path(earlier, point_id))
                if record["input"]["versions"][node_key(earlier, point_id)] != ancestor["selected_version"]:
                    raise ValueError("上游结果已修订，请先恢复运行至该节点再修订")
        revision = {"id": f"r{len(record['revisions']) + 1}", "time": now(), "resource_version": self.resource_version,
                    "replaces": record["selected_version"], "input": record["input"],
                    "raw": file.read_text(encoding="utf-8-sig")}
        if stage == "enrich":
            revision["upstream_versions"] = record["attempts"][-1]["upstream_versions"]
        record["revisions"].append(revision)
        try:
            revision["parsed"] = parse_json(revision["raw"])
            revision["output"] = nodes.validate(stage, revision["parsed"], record["input"]["previous"])
            record.update(output=revision["output"], selected_version=revision["id"])
        except Exception as error:
            revision["error"] = str(error)
            raise ValueError(f"{record['id']} 修订 {revision['id']}：{error}") from error
        finally:
            save(path, record)
        self.status("paused", revised=record["id"], version=revision["id"])

    def execute(self, pause_after):
        if self.manifest["status"] == "complete":
            return
        if pause_after:
            self.manifest["pause_after"] = pause_after
        pending = self.manifest.get("publishing")
        if pending and self.sidecar().is_file():
            detail = self.sidecar().read_bytes()
            if digest(detail) == pending:
                # Recover the exact staged pair even if the prompts changed after the first link.
                data = json.loads(detail)
                library = encoded(data["nodes"]["assemble"]["output"]["library"])
                if digest(library) != data["library_sha256"]:
                    raise ValueError("待发布的溯源与主库摘要不一致")
                self.publish(library, detail)
                self.status("complete", output=self.manifest["output"])
                return
        self.status("running")
        records = {}

        def checkpoint(stage):
            if stage == self.manifest.get("pause_after"):
                self.manifest.pop("pause_after")
                self.status("paused", stage=stage)
                return True
            return False

        identify_input = {"source": self.source, "previous": {"source": self.source}}
        identify = self.evaluate("identify", None, identify_input)
        records["identify"] = identify
        if checkpoint("identify"):
            return
        points = {p["id"]: p for p in identify["output"]["points"]}
        split_input = {"run_id": self.manifest["run_id"], "versions": {"identify": identify["selected_version"]},
                       "points": identify["output"]["points"]}
        split = self.evaluate("split", None, split_input, lambda: [
            {"run_id": self.manifest["run_id"], "point_id": pid,
             "knowledge_version": digest(encoded(point)), "identify_version": identify["selected_version"],
             "source_refs": point["source_refs"]}
            for pid, point in points.items()])
        records["split"] = split
        if checkpoint("split"):
            return
        branches = {pid: {"point": point} for pid, point in points.items()}

        def branch(stage, pid):
            branch_data = branches[pid]
            point = points[pid]
            previous = dict(branch_data)
            inputs = {"point": point, "previous": previous,
                      "versions": {node_key(s, pid): records[node_key(s, pid)]["selected_version"]
                                   for s in BRANCH_STAGES if s in branch_data}}
            if stage == "enrich":
                previous["source"] = inputs["source"] = self.source
                previous["related_points"] = [points[k] for k in point["related_ids"]]
                # An edit to an unrelated point must not resend this branch to the model.
                return self.evaluate(stage, pid, inputs, upstream_versions={
                    "identify": identify["selected_version"], "split": split["selected_version"]})
            return self.evaluate(stage, pid, inputs)

        with ThreadPoolExecutor(max_workers=self.manifest["jobs"]) as pool:
            for stage in BRANCH_STAGES:
                errors = []
                futures = {pool.submit(branch, stage, pid): pid for pid in points}
                for future in as_completed(futures):
                    pid = futures[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        errors.append(str(error))
                        continue
                    records[result["id"]] = result
                    branches[pid][stage] = result["output"]
                if errors:
                    raise ValueError("\n".join(errors))
                if checkpoint(stage):
                    return

        def assemble():
            library, links = nodes.assemble(branches)
            groups = trace_groups(library, links, branches)
            return {"library": library, "groups": groups}

        versions = {key: records[key]["selected_version"] for key in sorted(records)}
        result = self.evaluate("assemble", None, {"branches": branches, "versions": versions}, assemble)
        records["assemble"] = result
        if checkpoint("assemble"):
            return
        library = encoded(result["output"]["library"])
        groups = {}
        for gid, group in result["output"]["groups"].items():
            sentences = {}
            for sid, sentence in group["sentences"].items():
                selected = {key: records[key]["selected_version"] for key in sentence["node_ids"]}
                enrich = records[node_key("enrich", sentence["point_id"])]
                # Unchanged branches may still use an earlier identification/split attempt.
                selected.update(enrich["attempts"][-1]["upstream_versions"])
                sentences[sid] = {**sentence, "node_versions": selected}
            groups[gid] = {"sentences": sentences}
        detail = {"schema_version": 1, "run_id": self.manifest["run_id"],
                  "library_sha256": digest(library), "source_name": self.manifest["source_name"],
                  "resource_versions": self.manifest["resource_versions"], "groups": groups,
                  "nodes": {key: records[key] for key in sorted(records)}}
        detail_bytes = encoded(detail)
        self.manifest["publishing"] = digest(detail_bytes)
        self.status("publishing")
        self.publish(library, detail_bytes)
        self.status("complete", output=self.manifest["output"])

    def sidecar(self):
        main = Path(self.manifest["output"])
        return main.with_name(main.stem + "-detail.json")

    def publish(self, library, detail):
        main = Path(self.manifest["output"])
        sidecar = self.sidecar()
        # A reader can discover the main file only after its sidecar is durable.
        # Identical bytes also handle a crash between the two links or before the checkpoint.
        for path, expected in [(main, library), (sidecar, detail)]:
            if path.exists() and path.read_bytes() != expected:
                raise ValueError(f"输出文件已存在且内容不同：{path}")
        if main.exists() and not sidecar.exists():
            raise ValueError(f"该主库已存在且缺少本次运行的溯源文件：{main}")
        for path, expected in [(sidecar, detail), (main, library)]:
            try:
                write_bytes(path, expected, exclusive=True)
            except FileExistsError:
                if path.read_bytes() != expected:
                    raise ValueError(f"另一运行已占用输出文件：{path}")


def trace_groups(library, links, branches):
    groups = {}
    for group in library["groups"]:
        gid = group["id"]
        sentences = {}
        for utterance in group["utterances"]:
            sid = utterance["id"]
            link = links[gid][sid]
            pid = link["point_id"]
            branch = branches[pid]
            event = next((e for e in branch["events"]["events"] if e["id"] == link["event_id"]), None)
            condition = next((c for c in branch["conditions"]["conditions"] if c["id"] == link["condition_id"]), None)
            if not event or not condition or condition["event_id"] != event["id"] or sid in sentences:
                raise ValueError(f"句级溯源不完整：{gid} / {sid}")
            ids = ["identify", "split", *(node_key(s, pid) for s in BRANCH_STAGES), "assemble"]
            sentences[sid] = {**link, "node_ids": ids, "text": utterance["text"]}
        if not sentences or gid in groups or sentences.keys() != links[gid].keys():
            raise ValueError(f"组级溯源不完整：{gid}")
        groups[gid] = {"sentences": sentences}
    if not groups or groups.keys() != links.keys():
        raise ValueError("组目录与溯源索引不一致")
    return groups


def parser():
    cli = argparse.ArgumentParser(description="生成 v0.4 话术库并保留七个节点的输入、输出和修订。")
    commands = cli.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="从文字稿新建运行")
    start.add_argument("source", type=Path)
    start.add_argument("--output", type=Path, required=True)
    start.add_argument("--provider", default="codex", choices=("codex", "gemini", "openai"))
    start.add_argument("--model", required=True)
    start.add_argument("--jobs", type=int, default=4)
    resume = commands.add_parser("resume", help="恢复暂停或失败的运行")
    revise = commands.add_parser("revise", help="保存人工修订的模型输出 JSON")
    revise.add_argument("--stage", choices=("identify", *BRANCH_STAGES), required=True)
    revise.add_argument("--point")
    revise.add_argument("--file", type=Path, required=True)
    for command in (start, resume, revise):
        command.add_argument("--run-dir", type=Path, required=True)
    for command in (start, resume):
        command.add_argument("--pause-after", choices=STAGES)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    directory = args.run_dir.resolve()
    try:
        if args.command == "start":
            source = args.source.read_text(encoding="utf-8-sig")
            output = args.output.resolve()
            if output.suffix.lower() != ".json" or output.stem.lower().endswith("-detail"):
                raise ValueError("输出须为主库 JSON 文件")
            if not source.strip() or args.jobs < 1 or not args.model.strip():
                raise ValueError("需要非空文字稿、模型名称和至少一个并行任务")
            if output == directory / "run.json" or output.is_relative_to(directory / "nodes"):
                raise ValueError("输出文件与运行记录冲突")
            directory.mkdir(parents=True, exist_ok=True)
        with run_lock(directory):
            if args.command == "start":
                if any(p.name != ".lock" for p in directory.iterdir()):
                    raise ValueError(f"新运行需要空目录：{directory}")
                write_bytes(directory / "source.txt", source.encode())
                save(directory / "run.json", {"run_id": uuid4().hex, "status": "new", "source_name": args.source.name,
                                               "source_sha256": digest(source.encode()), "model": args.model,
                                               "provider": args.provider, "jobs": args.jobs, "output": str(output)})
            run = Run(directory)
            if args.command == "revise":
                run.revise(args.stage, args.point, args.file)
            else:
                try:
                    run.execute(args.pause_after)
                except Exception as error:
                    run.status("failed", error=str(error))
                    raise
            print(json.dumps({"status": run.manifest["status"], "run_dir": str(directory),
                              **run.manifest.get("checkpoint", {})}, ensure_ascii=False))
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
