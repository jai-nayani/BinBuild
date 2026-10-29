"""Run one camera batch through the whole loop, through the API, and report.

    upload 5 photos -> photo gate -> classify -> review -> confirm
      -> generator-ready vs everything else -> build (known set, BrickGPT via Path A)
      -> booklet, and undo -> the build no longer fits -> confirm again

Every stage goes through the HTTP endpoints the phone uses, on a throwaway
database and data folder: the real binbuild.db is never touched, and nothing
is edited by hand between stages.

No Baseten or Model API call. Spark is replaced by a recorded reply
(tests/fixtures/kit-batch-recorded.json) that is only played back for the
exact photos it was recorded on (sha256 per view). With --sam, classify also
runs the SAM 3.1 pass, with SAM's replies and Spark's close-up replies played
back from tests/fixtures/kit-batch-sam-recorded.json (each only for the exact
request it was recorded for). The review then brings every piece to its
verified label through the review endpoint, as a person would from the review
screen, and the report counts the corrections that took.

From the repo root (needs the backend requirements):
    python -m backend.full_loop                  # the kit batch; report under data/full-loop/
    python -m backend.full_loop --sam            # the same, with the SAM 3.1 pass
    python -m backend.full_loop --batch DIR --recorded FILE --out DIR --design train
"""

import argparse
import copy
import hashlib
import json
import socket
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
KIT_BATCH = REPO / "data" / "batches" / "20261028-192429-119901"
RECORDED = REPO / "tests" / "fixtures" / "kit-batch-recorded.json"
SAM_RECORDED = REPO / "tests" / "fixtures" / "kit-batch-sam-recorded.json"
FIELDS = ("family", "shape", "size", "color", "plain")
VIEWS = ("top", "front", "right", "back", "left")


class StageFailed(RuntimeError):
    pass


class ReplaySpark:
    """Stands in for SparkClient: plays back one recorded whole-photo reply
    and, for the SAM pass, recorded close-up replies (tiles: [{"count",
    "hints", "reply"}]), each only for a sheet with the same count and hints."""

    def __init__(self, recorded, tiles=()):
        self.recorded = recorded
        self.tiles = list(tiles)
        self.model = "replay:" + recorded.get("model", "meta-models/muse-spark-open-1026")
        self.calls = 0
        self.tile_calls = 0

    def name_tiles(self, sheet_jpeg, count, context=(), hints=None, max_tokens=0):
        from .spark_client import SparkError, SparkReply
        for rec in self.tiles:
            if rec["count"] == count and rec["hints"] == (list(hints) if hints else None):
                self.tile_calls += 1
                return copy.deepcopy(rec["reply"]), SparkReply("", "stop", {"replayed": True}, 0.0)
        raise SparkError(f"no recorded close-up reply for this sheet of {count}")

    def identify_pieces(self, image_jpeg, context=(), max_tokens=0):
        from .spark_client import SparkReply
        self.calls += 1
        reply = SparkReply("", self.recorded["recorded"]["finish_reason"], {"replayed": True}, 0.0)
        return copy.deepcopy(self.recorded["reply"]), reply


class ReplaySam:
    """Stands in for SamClient: plays back recorded SAM replies. A request is
    answered only if its image size and point prompts match a recorded one
    exactly; anything else is refused."""

    model = "replay:sam-3.1"

    def __init__(self, recorded):
        self.recorded = recorded  # [{"size": [w, h], "points": [[id, x, y], ...], "output": text}]
        self.requests = 0

    def segment_points(self, image_jpeg, size, points):
        from .sam_client import SamError, SamReply, parse_output
        want = [list(p) for p in points]
        for rec in self.recorded:
            if list(rec["size"]) == list(size) and [list(p) for p in rec["points"]] == want:
                self.requests += 1
                masks, diagnostics = parse_output(rec["output"])
                return SamReply(masks, 0.0, {"replayed": True}, rec["output"], diagnostics)
        raise SamError(f"no recorded SAM reply for these {len(want)} points")


class Api:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"

    def call(self, method, path, json_body=None, files=None, raw=False):
        body, headers = None, {}
        if files is not None:
            boundary = uuid.uuid4().hex
            body = b""
            for name, data in files:
                body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photos\"; filename=\"{name}\"\r\n"
                         "Content-Type: image/jpeg\r\n\r\n").encode() + data + b"\r\n"
            body += f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif json_body is not None:
            body = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as r:
                data = r.read()
                status = r.status
        except urllib.error.HTTPError as err:
            with err:
                data, status = err.read(), err.code
        return status, (data.decode() if raw else json.loads(data))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def server(workdir, spark, sam=None):
    """The real app on a free local port, with its database, data folder,
    Spark and SAM swapped for throwaway ones. Without sam, asking for the SAM
    pass fails as it would with no key: no real Model API call is possible."""
    import uvicorn
    from . import inventory_db, main
    from .sam_client import SamError
    patches = [mock.patch.object(inventory_db, "DB_PATH", Path(workdir) / "binbuild.db"),
               mock.patch.object(main, "DATA_DIR", Path(workdir) / "data"),
               mock.patch.object(main.SparkClient, "from_env", return_value=spark),
               mock.patch.object(main.SamClient, "from_env", **(
                   {"return_value": sam} if sam is not None else
                   {"side_effect": SamError("no Meta Model API key (test server)")}))]
    for p in patches:
        p.start()
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 15
        while not srv.started:
            if time.time() > deadline:
                raise StageFailed("the backend didn't start")
            time.sleep(0.05)
        yield Api(port)
    finally:
        srv.should_exit = True
        thread.join(timeout=5)
        for p in patches:
            p.stop()


def _expect(stage, status, want, body):
    if status != want:
        detail = body.get("detail") if isinstance(body, dict) else str(body)[:200]
        raise StageFailed(f"{stage}: HTTP {status}, expected {want}: {detail}")


def load_photos(batch_dir):
    """The batch's 5 photos in upload order, from its batch.json."""
    manifest = json.loads((Path(batch_dir) / "batch.json").read_text())
    files = {p["view"]: p["file"] for p in manifest["photos"]}
    return [(files[v], (Path(batch_dir) / files[v]).read_bytes()) for v in VIEWS]


def verified_summary(db_path):
    """The inventory summary in an existing database, read-only."""
    from . import inventory_db
    if not Path(db_path).is_file():
        return None
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return inventory_db.inventory_summary(conn)


def verified_labels(recorded) -> list:
    """Each piece's verified label, in reply order: Spark's piece, normalised
    as classify stores it, with the review's correction where there was one."""
    from .inventory_pipeline import to_detection
    from .segmenter import Region
    fixes = {r["piece"]: r for r in recorded["review"]}
    labels = []
    for n, piece in enumerate(recorded["reply"]["pieces"]):
        d = fixes[n] if n in fixes else to_detection(piece, Region((0, 0, 1, 1)))
        labels.append({k: d[k] for k in FIELDS})
    return labels


def run(batch_dir, recorded, out_dir, known_set="house-and-tree", design="train", sam_recorded=None) -> dict:
    """The whole loop. Raises StageFailed at the first stage that doesn't
    answer as expected; returns the report. sam_recorded: also run the SAM
    3.1 pass, played back from this recording."""
    photos = load_photos(batch_dir)
    for view, (_, data) in zip(VIEWS, photos):
        if hashlib.sha256(data).hexdigest() != recorded["photos_sha256"][view]:
            raise StageFailed(f"the recorded reply was not recorded on this batch's {view} photo; refusing to replay it")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spark = ReplaySpark(recorded, tiles=(sam_recorded or {}).get("tiles", ()))
    sam = ReplaySam(sam_recorded["sam"]) if sam_recorded else None
    stages = []
    report = {"batch": str(batch_dir), "recorded": recorded.get("about", ""), "stages": stages}

    def stage(name, started, **facts):
        stages.append({"stage": name, "seconds": round(time.perf_counter() - started, 2), **facts})

    with tempfile.TemporaryDirectory() as workdir, server(workdir, spark, sam) as api:
        t = time.perf_counter()
        status, up = api.call("POST", "/api/inventory/batch", files=photos)
        _expect("upload", status, 201, up)
        if not up["ready"]:
            raise StageFailed(f"photo gate: {[r['message'] for r in up['retake']]}")
        batch = up["batch_id"]
        stage("1. upload + photo gate", t, photos=len(photos),
              gate={p["view"]: p["gate_status"] for p in up["photos"]})

        t = time.perf_counter()
        status, cls = api.call("POST", f"/api/inventory/batch/{batch}/classify" + ("?segmenter=sam" if sam else ""))
        _expect("classify", status, 200, cls)
        checks = {v: c["answer"] for v, c in cls["run"]["calls"][0]["checks"].items()}
        stage("2. classify (recorded Spark reply)", t, spark_calls=spark.calls, pieces=cls["pieces"],
              real_lego_check=checks, classifier=cls["run"]["classifier"],
              recorded_live_seconds=recorded["recorded"]["seconds"])
        if sam:
            sp = cls["run"]["sam_pass"]
            stages[-1]["stage"] = "2. classify: whole photo, then SAM 3.1 close-ups (recorded replies)"
            stages[-1].update(classifier=sp["classifier"], sam_requests=sam.requests, masks=sp["masks"],
                              points=sp["points"], no_mask=sp["no_mask"], same_piece=sp["same_piece"],
                              spark_tile_calls=spark.tile_calls, recorded_live=sam_recorded["recorded"])

        t = time.perf_counter()
        detections = sorted(cls["detections"], key=lambda d: d["id"])
        verified = verified_labels(recorded)
        if len(detections) != len(verified):
            raise StageFailed(f"review: {len(detections)} proposals for {len(verified)} verified pieces")
        corrections, fixed, wording = [], [], []
        for n, (d, want) in enumerate(zip(detections, verified), 1):
            if all(d[k] == want[k] for k in FIELDS):
                corrections.append({"detection_id": d["id"], "status": "accepted"})
                continue
            (wording if all(d[k] == want[k] for k in FIELDS if k != "shape") else fixed).append(n)
            corrections.append({"detection_id": d["id"], **want, "status": "accepted"})
        status, rev = api.call("POST", f"/api/inventory/batch/{batch}/review", json_body={"corrections": corrections})
        _expect("review", status, 200, rev)
        status, conf = api.call("POST", f"/api/inventory/batch/{batch}/confirm")
        _expect("confirm", status, 200, conf)
        summary = conf["summary"]
        stage("3. review + confirm", t, corrected=len(fixed), corrected_pieces=fixed, shape_wording_only=len(wording),
              accepted=len(detections) - len(fixed) - len(wording),
              confirmed=conf.get("pieces_added", summary["total_pieces"]))

        t = time.perf_counter()
        status, opts = api.call("GET", "/api/builds/options")
        _expect("options", status, 200, opts)
        status, house = api.call("POST", "/api/builds", json_body={"set": known_set})
        _expect("known set", status, 201, house)
        booklet_file = None
        if "booklet_url" in house:
            status, page = api.call("GET", house["booklet_url"], raw=True)
            _expect("booklet", status, 200, page)
            booklet_file = out_dir / f"booklet-{known_set}.html"
            booklet_file.write_text(page)
        status, gpt = api.call("POST", "/api/builds", json_body={"design": design})
        _expect("BrickGPT design", status, 201, gpt)
        gpt_booklet = None
        if "booklet_url" in gpt:
            status, page = api.call("GET", gpt["booklet_url"], raw=True)
            _expect("booklet", status, 200, page)
            gpt_booklet = out_dir / f"booklet-{design}.html"
            gpt_booklet.write_text(page)
        stage("4. split + build + booklet", t,
              generator_ready=summary["generator_ready"]["total"], other=summary["other"]["total"],
              unknown=summary["unknown"]["total"],
              known_set={k: house.get(k) for k in ("status", "message", "steps")},
              brickgpt={k: gpt.get(k) for k in ("id", "status", "message", "shortfall", "short_bricks", "reason")})

        t = time.perf_counter()
        status, undo = api.call("POST", f"/api/inventory/undo-last-batch?batch_id={batch}")
        _expect("undo", status, 200, undo)
        status, after_undo = api.call("POST", "/api/builds", json_body={"set": known_set})
        _expect("known set after undo", status, 201, after_undo)
        status, again = api.call("POST", f"/api/inventory/batch/{batch}/confirm")
        _expect("confirm again", status, 200, again)
        status, after_redo = api.call("POST", "/api/builds", json_body={"set": known_set})
        _expect("known set after confirming again", status, 201, after_redo)
        stage("5. undo -> rebuild -> confirm -> rebuild", t, removed=undo["pieces_removed"],
              after_undo=after_undo["status"], after_confirm_again=after_redo["status"])

    report.update({
        "batch_id": batch, "summary": {k: summary[k] for k in ("total_pieces", "generator_ready", "other", "unknown", "items")},
        "options": [{k: o.get(k) for k in ("kind", "id", "status", "message")} for o in opts["options"]],
        "known_set": house, "brickgpt": gpt,
        "booklets": [str(f) for f in (booklet_file, gpt_booklet) if f],
        "spark_calls": spark.calls,
    })
    verified = verified_summary(REPO / "binbuild.db")
    if verified is not None:
        report["matches_verified_inventory"] = verified["items"] == summary["items"]
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--batch", type=Path, default=KIT_BATCH)
    parser.add_argument("--recorded", type=Path, default=RECORDED)
    parser.add_argument("--out", type=Path,
                        default=REPO / "data" / "full-loop" / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}")
    parser.add_argument("--set", default="house-and-tree")
    parser.add_argument("--design", default="train")
    parser.add_argument("--sam", action="store_true", help="also run the SAM 3.1 pass (recorded replies)")
    parser.add_argument("--sam-recorded", type=Path, default=SAM_RECORDED)
    args = parser.parse_args()
    report = run(args.batch, json.loads(args.recorded.read_text()), args.out, args.set, args.design,
                 json.loads(args.sam_recorded.read_text()) if args.sam else None)
    for s in report["stages"]:
        facts = {k: v for k, v in s.items() if k not in ("stage", "seconds")}
        print(f"{s['stage']} ({s['seconds']} s): {json.dumps(facts)}")
    if "matches_verified_inventory" in report:
        print("inventory matches the verified one in binbuild.db:", report["matches_verified_inventory"])
    print("booklets:", *report["booklets"], sep="\n  ")
    print("report:", args.out / "report.json")


if __name__ == "__main__":
    main()
