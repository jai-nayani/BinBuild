"""Meta Responses transport, bounded backup and API attribution, with fakes only."""

import io
import json
import os
import tempfile
import threading
import traceback
import unittest
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest import mock

from backend import full_loop, inventory_db, main, spark_client as sc
from test_photo_gate import scene
from test_sam import FakeSam

META_KEY, BASE_KEY = "fake-meta-secret-123", "fake-baseten-secret-456"
PIECE = {"family": "brick", "shape": "brick", "size": "1x2", "color": "red", "plain": True,
         "confidence": .9, "at": [.5, .5]}


def pieces(answer="yes", count=1):
    return {"checks": [{"image": n, "real_lego": answer} for n in range(1, 6)],
            "pieces": [dict(PIECE) for _ in range(count)]}


def meta(text=None, status="completed", reason=None):
    data = {"status": status, "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(pieces()) if text is None else text}]}],
        "usage": {"input_tokens": 7, "output_tokens": 11}}
    if reason:
        data["incomplete_details"] = {"reason": reason}
    return data


def baseten(text=None):
    return {"choices": [{"message": {"content": json.dumps(pieces()) if text is None else text},
                         "finish_reason": "stop"}], "usage": {"total_tokens": 5}}


def response(data):
    return io.BytesIO(json.dumps(data).encode())


def http_error(key, status=503):
    return urllib.error.HTTPError("https://api.invalid", status, "fake", {}, io.BytesIO(("bad " + key).encode()))


class Clock:
    now = 0

    def __call__(self):
        return self.now


class TestMetaSparkClient(unittest.TestCase):
    def test_text_jpeg_and_png_are_converted_without_changing_image_bytes(self):
        messages = [{"role": "system", "content": "Name the pieces"}, {"role": "user", "content": [
            {"type": "text", "text": "Look"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,SlBFRw=="}},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,UE5H"}},
        ]}]
        with mock.patch.object(sc.urllib.request, "urlopen", return_value=response(meta())) as opened:
            reply = sc.MetaSparkClient(META_KEY, timeout=37, retries=0).chat(messages, max_tokens=123, temperature=.25)
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.meta.ai/v1/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + META_KEY)
        self.assertEqual(opened.call_args.kwargs["timeout"], 37)
        body = json.loads(request.data)
        self.assertEqual(body["model"], sc.META_MODEL)
        self.assertEqual(body["max_output_tokens"], 123)
        self.assertNotIn("max_tokens", body)
        self.assertEqual(body["temperature"], .25)
        self.assertFalse(body["store"])
        self.assertEqual(body["input"], [
            {"type": "message", "role": "system", "content": [{"type": "input_text", "text": "Name the pieces"}]},
            {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "Look"},
                {"type": "input_image", "image_url": "data:image/jpeg;base64,SlBFRw=="},
                {"type": "input_image", "image_url": "data:image/png;base64,UE5H"},
            ]},
        ])
        self.assertEqual(reply.content, json.dumps(pieces()))
        self.assertEqual(reply.usage, {"input_tokens": 7, "output_tokens": 11})

    def test_finish_reason_and_output_text_mapping(self):
        for status, reason, expected in (("completed", None, "stop"),
                                         ("incomplete", "max_output_tokens", "length"),
                                         ("incomplete", "content_filter", "stop")):
            with self.subTest(status=status, reason=reason), mock.patch.object(sc.urllib.request, "urlopen",
                    return_value=response(meta('partial', status, reason))):
                reply = sc.MetaSparkClient(META_KEY, retries=0).chat([])
                self.assertEqual((reply.content, reply.finish_reason), ("partial", expected))
        with mock.patch.object(sc.urllib.request, "urlopen", return_value=response({"output_text": "plain text"})):
            self.assertEqual(sc.MetaSparkClient(META_KEY).chat([]).content, "plain text")
        with mock.patch.object(sc.urllib.request, "urlopen", return_value=response(meta('', 'incomplete', 'max_output_tokens'))):
            self.assertEqual(sc.MetaSparkClient(META_KEY).chat([]).finish_reason, "length")

    def test_retry_statuses_and_no_retry_for_unauthorized(self):
        for status in sorted(sc.RETRY_STATUS):
            with self.subTest(status=status), mock.patch.object(sc.urllib.request, "urlopen",
                    side_effect=[http_error(META_KEY, status), response(meta())]) as opened, \
                    mock.patch.object(sc.time, "sleep") as sleep:
                sc.MetaSparkClient(META_KEY, retries=1).chat([])
                self.assertEqual(opened.call_count, 2)
                sleep.assert_called_once_with(3)
        with mock.patch.object(sc.urllib.request, "urlopen", side_effect=http_error(META_KEY, 401)) as opened:
            with self.assertRaises(sc.SparkError):
                sc.MetaSparkClient(META_KEY, retries=2).chat([])
            self.assertEqual(opened.call_count, 1)

    def test_both_providers_scrub_keys_from_transport_and_reply_errors(self):
        for client, key in ((sc.MetaSparkClient(META_KEY, retries=0), META_KEY),
                            (sc.SparkClient(BASE_KEY, retries=0), BASE_KEY)):
            for kind in ("http", "http_read", "network", "unreadable", "json"):
                with self.subTest(provider=type(client).__name__, kind=kind):
                    effect = http_error(key) if kind == "http" else urllib.error.URLError(key) if kind == "network" else None
                    if kind == "http_read":
                        stream_error = mock.Mock()
                        stream_error.read.side_effect = TimeoutError(key)
                        effect = urllib.error.HTTPError('https://api.invalid', 503, 'fake', {}, stream_error)
                    data = meta(key) if isinstance(client, sc.MetaSparkClient) else baseten(key)
                    stream = io.BytesIO(("broken " + key).encode()) if kind == "json" else response(data)
                    with mock.patch.object(sc.urllib.request, "urlopen", side_effect=effect, return_value=stream):
                        try:
                            client.identify_pieces(b"jpeg")
                        except sc.SparkError as err:
                            self.assertNotIn(key, str(err))
                            self.assertNotIn(key, traceback.format_exc())
                        else:
                            self.fail("expected a scrubbed SparkError")
                    self.assertNotIn(key, repr(client))

    def test_http_error_does_not_expose_a_key_truncated_at_the_body_limit(self):
        for client, key in ((sc.MetaSparkClient(META_KEY, retries=0), META_KEY),
                            (sc.SparkClient(BASE_KEY, retries=0), BASE_KEY)):
            error = urllib.error.HTTPError('https://api.invalid', 401, 'fake', {},
                                          io.BytesIO(('x' * 490 + key).encode()))
            with mock.patch.object(sc.urllib.request, 'urlopen', side_effect=error):
                with self.assertRaises(sc.SparkError) as caught:
                    client.chat([])
            self.assertNotIn(key[:10], str(caught.exception))
            self.assertIn('[key]', str(caught.exception))


class TestFallbackSpark(unittest.TestCase):
    def client(self, budget=110):
        return sc.FallbackSpark(sc.MetaSparkClient(META_KEY, timeout=999, retries=2),
                                sc.SparkClient(BASE_KEY, timeout=999, retries=2), budget)

    def test_http_timeout_unreadable_and_cut_off_use_backup(self):
        for kind in ("http", "timeout", "unreadable", "cut_off", "invalid_envelope", "invalid_json"):
            client = self.client()
            seen = []

            def opened(request, timeout):
                seen.append((request.full_url, timeout))
                if request.full_url.startswith(sc.META_BASE_URL):
                    if kind == "http":
                        raise http_error(META_KEY)
                    if kind == "timeout":
                        raise TimeoutError(META_KEY)
                    if kind == "invalid_envelope":
                        return response([])
                    if kind == "invalid_json":
                        return io.BytesIO(b'not JSON')
                    return response(meta(META_KEY) if kind == "unreadable" else meta('', 'incomplete', 'max_output_tokens'))
                return response(baseten())

            with self.subTest(kind=kind), mock.patch.object(sc.urllib.request, "urlopen", side_effect=opened):
                data, reply = client.identify_pieces(b"jpeg")
            self.assertEqual(data, pieces())
            self.assertEqual(reply.finish_reason, "stop")
            self.assertEqual(len(seen), 2, "primary has no automatic retry")
            self.assertEqual(seen[0][1], 60)
            self.assertTrue(45 <= seen[1][1] <= 110)
            self.assertEqual(client.model, f"{sc.META_MODEL} + backup {sc.MODEL} (1 of 1 calls)")
            self.assertEqual(client.report()["answered_by"], [sc.MODEL])
            self.assertEqual(client.report()["fallbacks"], 1)
            self.assertTrue(client.report()["reasons"])
            self.assertNotIn(META_KEY, str(client.calls))
            self.assertNotIn(BASE_KEY, repr(client))

    def test_no_or_uncertain_is_returned_without_backup(self):
        for answer in ("no", "uncertain"):
            client = self.client()
            with self.subTest(answer=answer), mock.patch.object(sc.urllib.request, "urlopen",
                    return_value=response(meta(json.dumps(pieces(answer, 0))))) as opened:
                data, _ = client.identify_pieces(b"jpeg")
            self.assertEqual(data["checks"][0]["real_lego"], answer)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(client.report(), {"answered_by": [sc.META_MODEL], "fallbacks": 0, "reasons": []})
            self.assertEqual(client.model, sc.META_MODEL)

    def test_wrong_piece_count_and_incomplete_tile_count_do_not_trigger_backup(self):
        client = self.client()
        with mock.patch.object(sc.urllib.request, "urlopen", side_effect=[
                response(meta(json.dumps(pieces(count=2)))), response(meta('{"tiles":[]}'))]) as opened:
            data, _ = client.identify_pieces(b"jpeg")
            tiles, _ = client.name_tiles(b"jpeg", 9)
        self.assertEqual(len(data["pieces"]), 2)
        self.assertEqual(tiles, {"tiles": []})
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(client.report()["fallbacks"], 0)

    def test_backup_requires_at_least_45_seconds_and_uses_only_remaining_budget(self):
        for elapsed, succeeds in ((55, True), (56, False)):
            client, clock, seen = self.client(100), Clock(), []

            def opened(request, timeout):
                seen.append(timeout)
                if request.full_url.startswith(sc.META_BASE_URL):
                    clock.now = elapsed
                    raise TimeoutError("primary timed out " + META_KEY)
                clock.now += 4
                return response(baseten())

            with self.subTest(elapsed=elapsed), mock.patch.object(sc.time, "monotonic", clock), \
                    mock.patch.object(sc.urllib.request, "urlopen", side_effect=opened):
                if succeeds:
                    _, reply = client.identify_pieces(b"jpeg")
                    self.assertEqual(seen, [60, 45])
                    self.assertEqual(reply.seconds, 59, "elapsed time includes the failed primary")
                else:
                    with self.assertRaisesRegex(sc.SparkError, "primary timed out"):
                        client.identify_pieces(b"jpeg")
                    self.assertEqual(seen, [60])
                    self.assertEqual(client.calls[0]["answered_by"], None)
                    self.assertFalse(client.calls[0]["fallback"])

    def test_chat_cutoff_or_unreadable_json_can_fall_back_for_step_words(self):
        for data in (meta('not JSON'), meta('', 'incomplete', 'max_output_tokens')):
            client = self.client(180)
            with mock.patch.object(sc.urllib.request, "urlopen", side_effect=[response(data), response(baseten('{"steps":[]}'))]):
                reply = client.chat([])
            self.assertEqual(json.loads(reply.content), {"steps": []})
            self.assertEqual(client.report()["fallbacks"], 1)

    def test_both_failures_are_recorded_without_either_key(self):
        client = self.client()
        with mock.patch.object(sc.urllib.request, "urlopen", side_effect=[http_error(META_KEY), http_error(BASE_KEY)]):
            with self.assertRaises(sc.SparkError) as caught:
                client.identify_pieces(b"jpeg")
        for key in (META_KEY, BASE_KEY):
            self.assertNotIn(key, str(caught.exception))
            self.assertNotIn(key, str(client.calls))
        self.assertEqual(client.call_count, 1)
        self.assertIsNone(client.calls[0]["answered_by"])

    def test_parallel_tiles_count_the_actual_answering_models_without_timeout_races(self):
        client, barrier = self.client(), threading.Barrier(2)

        def opened(request, timeout):
            data = json.loads(request.data)
            if request.full_url.startswith(sc.META_BASE_URL):
                self.assertEqual(timeout, 60)
                image = next(p["image_url"] for p in data["input"][0]["content"] if p["type"] == "input_image")
                barrier.wait(3)
                if image.endswith("YmFja3Vw"):
                    raise http_error(META_KEY)
                return response(meta('{"tiles":[]}'))
            self.assertTrue(45 <= timeout <= 110)
            return response(baseten('{"tiles":[]}'))

        with mock.patch.object(sc.urllib.request, "urlopen", side_effect=opened), ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(client.name_tiles, image, 1) for image in (b"primary", b"backup")]
            for job in jobs:
                self.assertEqual(job.result()[0], {"tiles": []})
        self.assertEqual(Counter(client.report()["answered_by"]), Counter({sc.META_MODEL: 1, sc.MODEL: 1}))
        self.assertEqual(client.report()["fallbacks"], 1)
        self.assertEqual(client.model, f"{sc.META_MODEL} + backup {sc.MODEL} (1 of 2 calls)")
        self.assertEqual((client.primary.timeout, client.backup.timeout), (999, 999))


class TestSparkFactory(unittest.TestCase):
    def factory(self, mode=None, keys=None, budget=110):
        env = {k: v for k, v in os.environ.items() if k != 'BINBUILD_SPARK'}
        if mode is not None:
            env['BINBUILD_SPARK'] = mode
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sc, 'env_value',
                side_effect=lambda name, *args: (keys or {}).get(name, '')):
            return sc.make_spark(budget)

    def test_default_and_explicit_meta_plus_baseten_wrap_both_clients(self):
        for mode in (None, 'meta+baseten'):
            client = self.factory(mode, {'META_MODEL_API_KEY': META_KEY, 'BASETEN_API_KEY': BASE_KEY})
            self.assertIsInstance(client, sc.FallbackSpark)
            self.assertIsInstance(client.primary, sc.MetaSparkClient)
            self.assertIs(type(client.backup), sc.SparkClient)

    def test_missing_meta_key_uses_baseten_directly_and_records_why(self):
        client = self.factory(keys={'BASETEN_API_KEY': BASE_KEY})
        self.assertIsNone(client.primary)
        with mock.patch.object(sc.urllib.request, 'urlopen', return_value=response(baseten())) as opened:
            client.identify_pieces(b'jpeg')
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(opened.call_args.args[0].full_url, sc.BASE_URL + '/chat/completions')
        self.assertEqual(client.model, sc.MODEL)
        self.assertEqual(client.report(), {'answered_by': [sc.MODEL], 'fallbacks': 1, 'reasons': ['Meta Model API key missing']})

    def test_both_keys_missing_raise_and_a_missing_backup_does_not_disable_meta(self):
        with self.assertRaises(sc.SparkError):
            self.factory()
        client = self.factory(keys={'MODEL_API_KEY': META_KEY})
        self.assertIsNone(client.backup)
        with mock.patch.object(sc.urllib.request, 'urlopen', side_effect=TimeoutError('fake')):
            with self.assertRaises(sc.SparkError):
                client.identify_pieces(b'jpeg')

    def test_baseten_emergency_mode_is_the_original_client_and_wire_format(self):
        client = self.factory('baseten', {'BASETEN_API_KEY': BASE_KEY}, budget=80)
        self.assertIs(type(client), sc.SparkClient)
        with mock.patch.object(sc.urllib.request, 'urlopen', return_value=response(baseten())) as opened:
            client.identify_pieces(b'jpeg')
        request = opened.call_args.args[0]
        self.assertEqual(opened.call_args.kwargs['timeout'], 80)
        self.assertEqual(request.get_header('Authorization'), 'Api-Key ' + BASE_KEY)
        body = json.loads(request.data)
        self.assertEqual(body['model'], sc.MODEL)
        self.assertIn('messages', body)
        self.assertIn('max_tokens', body)
        self.assertNotIn('input', body)

    def test_meta_only_and_health_configuration_need_no_backup(self):
        client = self.factory('meta', {'MODEL_API_KEY': META_KEY})
        self.assertIs(type(client), sc.MetaSparkClient)
        self.assertEqual((client.model, client.timeout, client.retries), (sc.META_MODEL, 110, 0))
        for mode, expected in (('meta', [sc.META_MODEL]), ('baseten', [sc.MODEL]), ('meta+baseten', [sc.META_MODEL, sc.MODEL])):
            with mock.patch.dict(os.environ, {'BINBUILD_SPARK': mode}):
                self.assertEqual(sc.spark_configuration(), {'mode': mode, 'models': expected})
        with self.assertRaises(sc.SparkError):
            self.factory('typo')


class TestMetaSparkApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.photos = []
        for n in range(5):
            out = io.BytesIO()
            scene(seed=910 + n).save(out, 'JPEG', quality=92)
            cls.photos.append((f'{n}.jpg', out.getvalue()))

    def run_api(self, mode, handler):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ctx = full_loop.server(tmp.name, None, FakeSam(r=4))
        api = ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        for patcher in (mock.patch.dict(os.environ, {'BINBUILD_SPARK': mode}),
                        mock.patch.object(sc, 'env_value', side_effect=lambda name, *args: {
                            'META_MODEL_API_KEY': META_KEY, 'BASETEN_API_KEY': BASE_KEY}.get(name, '')),
                        mock.patch.object(main, 'make_spark', side_effect=sc.make_spark)):
            patcher.start()
            self.addCleanup(patcher.stop)
        real_open = urllib.request.urlopen

        def opened(request, timeout=120):
            if request.full_url.startswith(api.base):
                return real_open(request, timeout=timeout)
            return handler(request, timeout)

        patcher = mock.patch.object(sc.urllib.request, 'urlopen', side_effect=opened)
        patcher.start()
        self.addCleanup(patcher.stop)
        status, uploaded = api.call('POST', '/api/inventory/batch', files=self.photos)
        self.assertEqual(status, 201, uploaded)
        self.assertTrue(uploaded['ready'])
        return api, uploaded['batch_id']

    def test_meta_only_classify_stores_proposals_and_names_the_answering_model(self):
        calls = []

        def opened(request, timeout):
            calls.append(request.full_url)
            return response(meta())

        api, batch = self.run_api('meta', opened)
        status, body = api.call('POST', f'/api/inventory/batch/{batch}/classify?segmenter=stub')
        self.assertEqual(status, 200, body)
        self.assertEqual(main.make_spark.call_args, mock.call(110))
        self.assertEqual(body['pieces'], 1)
        self.assertIn('spark:muse-spark-1.3 ', body['batch']['classifier'])
        self.assertEqual(body['run']['spark'], {'answered_by': [sc.META_MODEL], 'fallbacks': 0, 'reasons': []})
        with closing(inventory_db.connect()) as conn:
            stored = inventory_db.batch_review(conn, batch)
        self.assertEqual(len(stored['detections']), 1)
        self.assertEqual(calls, [sc.META_BASE_URL + '/responses'])
        self.assertEqual(api.call('GET', '/health')[1]['spark'], {'mode': 'meta', 'models': [sc.META_MODEL]})

    def test_mixed_sam_sheets_name_the_backup_in_classifier_and_report(self):
        primary_tiles = 0
        whole = pieces(count=17)
        for n, piece in enumerate(whole['pieces']):
            piece['at'] = [.1 + .15 * (n % 5), .1 + .18 * (n // 5)]
        lock = threading.Lock()

        def opened(request, timeout):
            nonlocal primary_tiles
            text = json.dumps({'tiles': [dict(PIECE, tile=n) for n in range(1, 17)]})
            if request.full_url.startswith(sc.META_BASE_URL):
                prompt = json.loads(request.data)['input'][0]['content'][0]['text']
                if 'numbered tiles' not in prompt:
                    return response(meta(json.dumps(whole)))
                with lock:
                    primary_tiles += 1
                    number = primary_tiles
                if number == 2:
                    raise http_error(META_KEY)
                return response(meta(text))
            return response(baseten(text))

        api, batch = self.run_api('meta+baseten', opened)
        path = f'/api/inventory/batch/{batch}/classify'
        self.assertEqual(api.call('POST', path + '?segmenter=stub')[0], 200)
        status, body = api.call('POST', path + '?segmenter=sam')
        self.assertEqual(status, 200, body)
        self.assertIn(f'spark:{sc.META_MODEL} + backup {sc.MODEL} (1 of 2 calls)', body['batch']['classifier'])
        report = body['run']['sam_pass']['spark']
        self.assertEqual(Counter(report['answered_by']), Counter({sc.META_MODEL: 1, sc.MODEL: 1}))
        self.assertEqual(report['fallbacks'], 1)
        self.assertNotIn(META_KEY, json.dumps(report))

    def test_missing_both_keys_returns_503_before_any_model_call(self):
        def opened(*args):
            self.fail('model called without keys')
        api, batch = self.run_api('meta+baseten', opened)
        with mock.patch.object(sc, 'env_value', return_value=''):
            status, body = api.call('POST', f'/api/inventory/batch/{batch}/classify?segmenter=stub')
        self.assertEqual(status, 503, body)
