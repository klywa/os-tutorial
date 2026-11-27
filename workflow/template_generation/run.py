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
    from . import base_library, nodes, providers, scenario_discovery, seed_nodes
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from workflow.template_generation import base_library, nodes, providers, scenario_discovery, seed_nodes


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
    resources = {p.relative_to(base).as_posix(): digest(p.read_bytes())
                 for folder in ("prompts", "references", "knowledge")
                 for p in sorted((base / folder).rglob("*")) if p.is_file()}
    resources["src/condition/catalog-v04.json"] = digest(encoded(nodes.catalog()))
    return resources


def validate_node_config(config):
    if not isinstance(config, dict):
        raise ValueError("节点模型配置必须是以阶段名为键的 JSON 对象")
    for stage, route in config.items():
        if stage not in nodes.STAGES:
            raise ValueError(f"不支持配置模型的阶段：{stage}")
        if not isinstance(route, dict) or route.get("provider") not in ("codex", "gemini", "openai"):
            raise ValueError(f"{stage} 的 provider 须为 codex、gemini 或 openai")
        model = route.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"{stage} 需要填写 model")
        allowed = {"provider", "model"}
        if route["provider"] == "openai":
            allowed.update(("base_url", "api_key_env", "allow_http"))
        if route.keys() - allowed:
            raise ValueError(f"{stage} 含不支持的模型配置字段：{', '.join(sorted(route.keys() - allowed))}")
        if "api_key_env" in route:
            name = route["api_key_env"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError(f"{stage} 的 api_key_env 必须是环境变量名")
        allow_http = route.get("allow_http", False)
        if not isinstance(allow_http, bool) or (allow_http and "base_url" not in route):
            raise ValueError(f"{stage} 的 allow_http 须为布尔值，启用时需要填写 base_url")
        if "base_url" in route:
            try:
                providers.compatible_base_url(route["base_url"], allow_http=allow_http)
            except ValueError as error:
                raise ValueError(f"{stage} 的 base_url 无效：{error}") from error
    return config


class Run:
    def __init__(self, directory):
        self.directory = directory
        self.manifest = read(directory / "run.json")
        self.node_config = validate_node_config(self.manifest.get("node_config", {}))
        self.source = (directory / "source.txt").read_text(encoding="utf-8")
        if digest(self.source.encode()) != self.manifest["source_sha256"]:
            raise ValueError("运行目录中的原文与初始版本不一致")
        resources = resource_versions()
        self.resource_version = digest(encoded(resources))
        self.generation_version = digest(encoded({k: v for k, v in resources.items() if k != "prompts/repair.md"}))
        self.manifest.setdefault("resource_versions", {})[self.resource_version] = resources
        self.base = None
        self.base_trace = None
        if "base_library_sha256" in self.manifest:
            snapshot = (directory / "base-library.json").read_bytes()
            if digest(snapshot) != self.manifest["base_library_sha256"]:
                raise ValueError("运行目录中的已有库与初始版本不一致")
            self.base = base_library.migrate(parse_json(snapshot.decode("utf-8-sig")))
            if "base_trace_sha256" in self.manifest:
                trace = (directory / "base-trace.json").read_bytes()
                if digest(trace) != self.manifest["base_trace_sha256"]:
                    raise ValueError("运行目录中的历史溯源与初始版本不一致")
                self.base_trace = parse_json(trace.decode("utf-8-sig"))
        self.local_replies = None
        if "local_replies_sha256" in self.manifest:
            snapshot = (directory / "local-replies.json").read_bytes()
            if digest(snapshot) != self.manifest["local_replies_sha256"]:
                raise ValueError("本地节点回复和运行快照不一致")
            self.local_replies = parse_json(snapshot.decode("utf-8-sig"))

    def signature(self, inputs, stage):
        versions = [self.generation_version]
        if stage in self.node_config:
            versions.append(self.node_config[stage])
        if self.local_replies is not None:
            versions.append(self.manifest["local_replies_sha256"])
        if "seed" in inputs.get("previous", {}) or "base_library_sha256" in inputs:
            versions.extend(digest(Path(module.__file__).read_bytes()) for module in (base_library, seed_nodes))
        return digest(encoded([inputs, *versions]))

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
        signature = self.signature(inputs, stage)
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
                route = self.node_config.get(stage, {
                    "provider": self.manifest["provider"], "model": self.manifest["model"],
                })
                attempt.update(kind="model", **route)
                handler = seed_nodes if "seed" in inputs["previous"] else nodes
                prompt = handler.prepare(stage, inputs.get("source", ""), inputs.get("point"), inputs["previous"])
                if self.local_replies is not None and stage == "phrases":
                    prompt += "\n\n本地审编回复直接提交 6 条已逐句审读的话术及其依据。"
                if previous.get("error") and "raw" in previous:
                    repair = Path(__file__).with_name("prompts") / "repair.md"
                    failure = {"error": previous["error"], "raw": previous["raw"]}
                    prompt += "\n\n" + repair.read_text(encoding="utf-8").strip() + "\n" + json.dumps(failure, ensure_ascii=False)
                    attempt["repairs"] = previous["id"]
                attempt["prompt"] = prompt
                save(path, record)
                if self.local_replies is None:
                    raw = providers.generate(prompt=prompt, **route)
                else:
                    attempt["kind"] = "local_reply"
                    if key not in self.local_replies:
                        raise ValueError(f"缺少本地节点回复：{key}")
                    raw = encoded(self.local_replies[key]).decode()
                attempt["raw"] = raw
                attempt["parsed"] = parse_reply(raw)
                if previous.get("insufficient_phrases"):
                    output = handler.validate(stage, attempt["parsed"], inputs["previous"], after_retry=True)
                else:
                    output = handler.validate(stage, attempt["parsed"], inputs["previous"])
            attempt["output"] = output
            record.update(output=output, selected_version=attempt["id"])
        except Exception as error:
            attempt["error"] = str(error)
            if isinstance(error, nodes.InsufficientPhrases):
                attempt["insufficient_phrases"] = True
                raise
            if isinstance(error, nodes.ConditionCoverageError):
                raise
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
        if record["signature"] != self.signature(record["input"], stage):
            raise ValueError("节点资料已更新，请先恢复运行至该节点再修订")
        if point_id is not None:
            enrich = read(self.node_path("enrich", point_id))
            previous = enrich["input"]["previous"]
            if "seed" not in previous:
                identify = read(self.node_path("identify", None))
                current = {p["id"]: p for p in identify["output"]["points"]}
                if current.get(point_id) != previous["point"] or any(
                        current.get(p["id"]) != p for p in previous["related_points"]):
                    raise ValueError("识别结果已修订，请先恢复运行至该节点再修订")
            for earlier in BRANCH_STAGES[:BRANCH_STAGES.index(stage)]:
                ancestor = read(self.node_path(earlier, point_id))
                if record["input"]["versions"][node_key(earlier, point_id)] != ancestor["selected_version"]:
                    raise ValueError("上游结果已修订，请先恢复运行至该节点再修订")
        revision = {"id": f"r{len(record['revisions']) + 1}", "time": now(), "resource_version": self.resource_version,
                    "replaces": record["selected_version"] or record["attempts"][-1]["id"], "input": record["input"],
                    "raw": file.read_text(encoding="utf-8-sig")}
        if stage == "enrich":
            revision["upstream_versions"] = record["attempts"][-1]["upstream_versions"]
        record["revisions"].append(revision)
        try:
            revision["parsed"] = parse_json(revision["raw"])
            previous = record["input"]["previous"]
            handler = seed_nodes if "seed" in previous else nodes
            revision["output"] = handler.validate(stage, revision["parsed"], previous)
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
                library = encoded(read(self.node_path("assemble", None))["output"]["library"])
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
        segments = None
        if self.base is not None:
            segments = scenario_discovery.source_segments(self.source)
            identify_input["previous"]["segments"] = segments
        identify = self.evaluate("identify", None, identify_input)
        records["identify"] = identify
        if checkpoint("identify"):
            return
        points = {p["id"]: p for p in identify["output"]["points"]}
        seeds = {}
        base_groups = {}
        if self.base is not None:
            for group in self.base["groups"]:
                base_groups[group["id"]] = {key: value for key, value in group.items() if key in {
                    "id", "name", "event_name", "extra_key", "scope", "expression", "priority",
                    "instruction", "ignored", "publication_hold"}}
                if not group["utterances"]:
                    point = base_library.seed_point(group, self.source)
                    if point["id"] in points:
                        raise ValueError("知识点 ID 与已有空组冲突：" + point["id"])
                    points[point["id"]] = point
                    seeds[point["id"]] = group
        split_input = {"run_id": self.manifest["run_id"], "versions": {"identify": identify["selected_version"]},
                       "points": list(points.values())}
        split = self.evaluate("split", None, split_input, lambda: [
            {"run_id": self.manifest["run_id"], "point_id": pid,
             "knowledge_version": digest(encoded(point)), "identify_version": identify["selected_version"],
             "source_refs": point["source_refs"], **({"base_group_id": seeds[pid]["id"]} if pid in seeds else {})}
            for pid, point in points.items()])
        records["split"] = split
        if checkpoint("split"):
            return
        pause_stage = self.manifest.get("pause_after")
        branch_stages = BRANCH_STAGES
        if pause_stage in BRANCH_STAGES:
            branch_stages = BRANCH_STAGES[:BRANCH_STAGES.index(pause_stage) + 1]

        def branch(pid):
            point = points[pid]
            branch_data = {"point": point}
            if self.local_replies is not None:
                branch_data["local_replies"] = True
            if pid in seeds:
                branch_data["seed"] = seeds[pid]
            elif self.base is not None:
                branch_data["scenario_discovery"] = True
            branch_records = {}
            for stage in branch_stages:
                previous = dict(branch_data)
                inputs = {"point": point, "previous": previous,
                          "versions": {key: record["selected_version"] for key, record in branch_records.items()}}
                upstream_versions = None
                if stage == "enrich":
                    previous["source"] = inputs["source"] = self.source
                    previous["related_points"] = [points[k] for k in point["related_ids"]]
                    # An edit to an unrelated point must not resend this branch to the model.
                    upstream_versions = {"identify": identify["selected_version"], "split": split["selected_version"]}
                if stage == "conditions" and pid not in seeds and base_groups:
                    event_names = {row["event"] for row in previous["events"]["events"]}
                    branch_data["base_groups"] = previous["base_groups"] = {
                        gid: group for gid, group in base_groups.items() if group["event_name"] in event_names}
                try:
                    result = self.evaluate(stage, pid, inputs, upstream_versions=upstream_versions)
                except (nodes.InsufficientPhrases, nodes.ConditionCoverageError):
                    result = self.evaluate(stage, pid, inputs, upstream_versions=upstream_versions)
                except ValueError:
                    if self.base is None:
                        raise
                    last = read(self.node_path(stage, pid))["attempts"][-1]
                    if "raw" not in last:
                        raise
                    result = self.evaluate(stage, pid, inputs, upstream_versions=upstream_versions)
                branch_records[result["id"]] = result
                branch_data[stage] = result["output"]
            return branch_data, branch_records

        branches = {}
        errors = {}
        with ThreadPoolExecutor(max_workers=self.manifest["jobs"]) as pool:
            futures = {pool.submit(branch, pid): pid for pid in points}
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    branches[pid], branch_records = future.result()
                except Exception as error:
                    errors[pid] = str(error)
                    continue
                records.update(branch_records)
        if errors:
            raise ValueError("\n".join(errors[pid] for pid in points if pid in errors))
        if checkpoint(branch_stages[-1]):
            return
        branches = {pid: branches[pid] for pid in points}

        def assemble():
            if self.base is None:
                library, links = nodes.assemble(branches)
                return {"library": library, "groups": trace_groups(library, links, branches)}
            discovered, links, checks = nodes.assemble(
                {pid: row for pid, row in branches.items() if pid not in seeds}, defer_playability=True)
            fills, filled_links, fixed_checks = seed_nodes.collect({pid: branches[pid] for pid in seeds})
            library, duplicates = base_library.merge(self.base, fills, discovered)
            discovered_links = dict(links)
            for gid in duplicates:
                del links[gid]
            refinements = {}
            for gid, sentences in links.items():
                link = next(iter(sentences.values()))
                conditions = branches[link["point_id"]]["conditions"]["conditions"]
                condition = next(row for row in conditions if row["id"] == link["condition_id"])
                if "base_group_id" in condition:
                    refinements[gid] = condition["base_group_id"]
            links.update(filled_links)
            base_library.validate_library(library)
            base_library.check_playability(library, {**checks, **fixed_checks}, refinements)
            retained = [g["id"] for g in self.base["groups"] if g["utterances"]]
            groups = trace_groups(library, links, branches, retained=retained)
            coverage = scenario_discovery.report(segments, identify["output"]["coverage"], branches, links,
                                                 discovered_links, duplicates, refinements)
            return {"library": library, "groups": groups, "duplicate_groups": duplicates,
                    "retained_groups": retained, "coverage": coverage}

        versions = {key: records[key]["selected_version"] for key in sorted(records)}
        assemble_input = {"branches": branches, "versions": versions}
        if self.base is not None:
            assemble_input["base_library_sha256"] = self.manifest["base_library_sha256"]
        result = self.evaluate("assemble", None, assemble_input, assemble)
        records["assemble"] = result
        if checkpoint("assemble"):
            return
        library = encoded(result["output"]["library"])
        detail = review_trace(self.manifest, library, result["output"]["groups"], branches, records)
        if self.local_replies is not None:
            detail["local_replies_sha256"] = self.manifest["local_replies_sha256"]
        if self.base is not None:
            retained_ids = set(result["output"]["retained_groups"])
            inherited = base_library.inherit_trace(detail, self.base_trace,
                [group for group in self.base["groups"] if group["id"] in retained_ids])
            detail["base_library"] = {"name": self.manifest["base_library_name"],
                                     "sha256": self.manifest["base_library_sha256"],
                                     "duplicate_groups": result["output"]["duplicate_groups"],
                                     "retained_with_history": sorted(inherited),
                                     "retained_without_new_trace": sorted(retained_ids - inherited)}
            detail["coverage"] = result["output"]["coverage"]
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


def trace_groups(library, links, branches, *, retained=()):
    groups = {}
    for group in library["groups"]:
        gid = group["id"]
        if gid in retained:
            continue
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
            sentences[sid] = {**link, "text": utterance["text"]}
        if not sentences or gid in groups or sentences.keys() != links[gid].keys():
            raise ValueError(f"组级溯源不完整：{gid}")
        groups[gid] = {"sentences": sentences}
    if (not groups and not retained) or groups.keys() != links.keys():
        raise ValueError("组目录与溯源索引不一致")
    return groups


def review_trace(manifest, library, groups, branches, records):
    """Project the adopted model outputs. Full attempts stay in the run directory."""
    details = {"schema_version": 2, "run_id": manifest["run_id"],
               "library_name": Path(manifest["output"]).name, "library_sha256": digest(library),
               "knowledge_lists": {}, "prompts": {}, "points": {}, "groups": {}}

    def version(key, version_id):
        record = records[key]
        return next(row for row in (*record["attempts"], *record["revisions"]) if row["id"] == version_id)

    def prompt_id(key, adopted):
        while "replaces" in adopted:
            if adopted.get("manual_only"):
                return None
            adopted = version(key, adopted["replaces"])
        if "prompt" not in adopted:
            return None
        ref = f"{key}/{adopted['id']}"
        details["prompts"][ref] = adopted["prompt"]
        return ref

    def knowledge_item(point, points):
        related = [*point["related_refs"],
                   *(ref for pid in point["related_ids"] for ref in points[pid]["source_refs"])]
        return {"original": "\n".join(ref["quote"] for ref in point["source_refs"]),
                "type": point["type"], "prerequisite": point["prerequisite"],
                "related_knowledge": "\n".join(dict.fromkeys(ref["quote"] for ref in related))}

    def pick(row, *fields):
        return {field: row[field] for field in fields}

    prompts_by_point = {}
    for pid, branch in branches.items():
        adopted = {}
        for stage in BRANCH_STAGES:
            key = node_key(stage, pid)
            adopted[stage] = version(key, records[key]["selected_version"])
        prompts = {stage: prompt_id(node_key(stage, pid), row) for stage, row in adopted.items()}
        if "seed" in branch:
            identify_id = pid
            details["knowledge_lists"][identify_id] = [knowledge_item(branch["point"], {})]
        else:
            identify_id = adopted["enrich"]["upstream_versions"]["identify"]
            identification = version("identify", identify_id)
            if identify_id not in details["knowledge_lists"]:
                points = {point["id"]: point for point in identification["output"]["points"]}
                details["knowledge_lists"][identify_id] = [knowledge_item(point, points) for point in points.values()]
            prompts["identify"] = prompt_id("identify", identification)
        prompts_by_point[pid] = identify_id, {stage: ref for stage, ref in prompts.items() if ref is not None}
        details["points"][pid] = {
            "type": branch["point"]["type"],
            "knowledge": branch["enrich"]["knowledge"],
            "events": [pick(row, "id", "event", "expected") for row in branch["events"]["events"]],
            "conditions": [
                {**pick(row, "id", "event_id", "reason", "limited", "not_limited", "expected", "wording"),
                 **({"extra_key": row["extra_key"]} if "extra_key" in row else {}),
                 "expression": nodes.effective_expression(row["scope"], row["expression"])}
                for row in branch["conditions"]["conditions"]],
            "rejected": branch["conditions"].get("rejected", []),
        }
    for gid, group in groups.items():
        sentences = group["sentences"]
        first = next(iter(sentences.values()))
        pid, cid = first["point_id"], first["condition_id"]
        identify_id, prompts = prompts_by_point[pid]
        phrases = next(row for row in branches[pid]["phrases"]["groups"] if row["condition_id"] == cid)
        details["groups"][gid] = {
            **pick(first, "point_id", "event_id", "condition_id"),
            "knowledge_list_id": identify_id,
            "prompt_ids": prompts,
            "writing": phrases["writing"],
            "sentences": {sid: row["text"] for sid, row in sentences.items()},
        }
    return details


def parser():
    cli = argparse.ArgumentParser(description="生成 v0.5 话术库并保留七个节点的输入、输出和修订。")
    commands = cli.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="从文字稿新建运行")
    start.add_argument("source", type=Path)
    start.add_argument("--output", type=Path, required=True)
    start.add_argument("--base-library", type=Path, help="加载已有 v0.4 或 v0.5 模板库，补全空组并追加新发现的组")
    start.add_argument("--provider", default="codex", choices=("codex", "gemini", "openai", "local"))
    start.add_argument("--local-replies", type=Path, help="使用本地审编节点回复 JSON，在本机跑同一套校验和发布")
    start.add_argument("--model", required=True)
    start.add_argument("--node-config", type=Path, help="指定各模型阶段使用的 provider、model 和 API 设置 JSON")
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
            base_meta = {}
            base_trace = None
            local_meta = {}
            if (args.provider == "local") != bool(args.local_replies):
                raise ValueError("需要同时指定 --provider local 和 --local-replies")
            if args.node_config and args.local_replies:
                raise ValueError("--node-config 不能与 --provider local 一起使用")
            node_config = {"node_config": validate_node_config(read(args.node_config))} if args.node_config else {}
            if args.local_replies:
                local_snapshot = args.local_replies.read_bytes()
                nodes._object(parse_json(local_snapshot.decode("utf-8-sig")), "本地节点回复")
                local_meta = {"local_replies_sha256": digest(local_snapshot)}
            if args.base_library:
                base_path = args.base_library.resolve()
                if base_path == output:
                    raise ValueError("已有库与输出文件须使用不同路径")
                snapshot = base_path.read_bytes()
                base_library.validate_library(base_library.migrate(parse_json(snapshot.decode("utf-8-sig"))), draft=True)
                base_meta = {"base_library_name": base_path.name, "base_library_sha256": digest(snapshot)}
                prior_path = base_path.with_name(base_path.stem + "-detail.json")
                if prior_path.is_file():
                    candidate = prior_path.read_bytes()
                    try:
                        prior = parse_json(candidate.decode("utf-8-sig"))
                    except (ValueError, UnicodeError):
                        prior = None
                    if (isinstance(prior, dict) and prior.get("schema_version") == 2
                            and prior.get("library_name") == base_path.name
                            and prior.get("library_sha256") == base_meta["base_library_sha256"]):
                        base_trace = candidate
                        base_meta["base_trace_sha256"] = digest(candidate)
            if output.suffix.lower() != ".json" or output.stem.lower().endswith("-detail"):
                raise ValueError("输出须为主库 JSON 文件")
            if not source.strip() or args.jobs < 1 or not args.model.strip():
                raise ValueError("需要非空文字稿、模型名称和至少一个并行任务")
            reserved = {"run.json", "base-library.json", "base-trace.json", "local-replies.json"}
            if (output.parent == directory and output.name in reserved) or output.is_relative_to(directory / "nodes"):
                raise ValueError("输出文件与运行记录冲突")
            directory.mkdir(parents=True, exist_ok=True)
        with run_lock(directory):
            if args.command == "start":
                if any(p.name != ".lock" for p in directory.iterdir()):
                    raise ValueError(f"新运行需要空目录：{directory}")
                write_bytes(directory / "source.txt", source.encode())
                if base_meta:
                    write_bytes(directory / "base-library.json", snapshot)
                if base_trace is not None:
                    write_bytes(directory / "base-trace.json", base_trace)
                if local_meta:
                    write_bytes(directory / "local-replies.json", local_snapshot)
                save(directory / "run.json", {"run_id": uuid4().hex, "status": "new", "source_name": args.source.name,
                                               "source_sha256": digest(source.encode()), "model": args.model,
                                               "provider": args.provider, "jobs": args.jobs, "output": str(output),
                                               **base_meta, **local_meta, **node_config})
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
