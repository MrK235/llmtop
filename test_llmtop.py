import json
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import llmtop_metrics as llmtop
import llmtop_tui


def test_run_metric_detail():
    assert llmtop.run_metric_detail({}) == 'Tokens: warten auf Provider · Tok/s: n/a'
    text = llmtop.run_metric_detail({'prompt_tokens': 1000, 'output_tokens': 250,
                                   'eval_duration_s': 5})
    assert text == 'Tokens: 1.2k (Prompt 1.0k, Ausgabe 250) · 50.0 Tok/s'
    text = llmtop.run_metric_detail({'prompt_tokens': 10, 'output_tokens': 3})
    assert text == 'Tokens: 13 (Prompt 10, Ausgabe 3) · Tok/s: n/a'
    assert 'Prompt n/a' in llmtop.run_metric_detail({'output_tokens': 3})


def test_run_history_defaults_to_hundred():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'runs.jsonl'
        records = []
        for index in range(102):
            stamp = f'2026-10-31T18:{index % 60:02d}:00Z'
            records.append({
                'schema': 2, 'run_id': str(index), 'source': 'open-webui',
                'model': 'model', 'status': 'completed',
                'started_at': stamp, 'updated_at': stamp, 'finished_at': stamp,
                'prompt_tokens': index, 'output_tokens': 1,
            })
        path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        result = llmtop.load_run_history(path)
        assert len(result) == 100


def test_clear_run_history():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'runs.jsonl'
        record = {
            'schema': 2, 'run_id': 'clear-me', 'source': 'pi', 'model': 'model',
            'status': 'completed', 'finished_at': '2026-11-02T21:00:00Z',
        }
        path.write_text(json.dumps(record) + '\n')
        assert llmtop.load_run_history(path)
        assert llmtop.clear_run_history(path)
        assert llmtop.load_run_history(path) == []
        assert path.read_text() == ''


def test_history_sorting_and_context_cells():
    runs = [
        {'run_id': 'a', 'source': 'open-webui', 'model': 'Beta', 'status': 'completed',
         'finished_at': '2026-10-31T18:01:00Z', 'prompt_tokens': 100, 'output_tokens': 50,
         'context_tokens': 150, 'context_limit': 1000, 'total_duration_s': 5, 'eval_duration_s': 1},
        {'run_id': 'b', 'source': 'pi', 'model': 'alpha', 'status': 'error',
         'finished_at': '2026-10-31T18:02:00Z', 'prompt_tokens': 600, 'output_tokens': 600,
         'context_tokens': 1200, 'context_limit': 1000, 'total_duration_s': 3, 'eval_duration_s': 2},
        {'run_id': 'c', 'source': 'ollama-cli', 'model': 'gamma', 'status': 'completed',
         'finished_at': '2026-10-31T18:03:00Z'},
    ]
    for column in llmtop.HISTORY_COLUMNS:
        ordered = llmtop.sort_run_history(runs, column)
        assert len(ordered) == 3
    assert llmtop.sort_run_history(runs, 'tokens')[-1]['run_id'] == 'c'
    assert llmtop.sort_run_history(runs, 'kontext')[-1]['run_id'] == 'c'
    percentage_runs = [
        dict(runs[0], run_id='large', context_tokens=1000, context_limit=10000),
        dict(runs[0], run_id='small', context_tokens=500, context_limit=1000),
    ]
    assert [item['run_id'] for item in llmtop.sort_run_history(
        percentage_runs, 'kontext')] == ['small', 'large']
    assert [item['run_id'] for item in llmtop.sort_run_history(runs, 'modell', False)] == ['b', 'a', 'c']
    assert llmtop.history_header_label('kontext', 'kontext', True) == 'Kontext▾'
    assert llmtop.history_header_label('kontext', 'kontext', False) == 'Kontext▴'
    assert llmtop.history_header_label('modell', 'kontext', True) == 'Modell'
    assert llmtop.history_context_cell(runs[0]) == '15% 150/1.0k'
    assert llmtop.history_context_cell(dict(runs[0], context_limit=None)) == 'n/a 150/n/a'
    assert llmtop.history_context_cell(runs[2]) == 'n/a'


def test_history_groups_keep_all_runs_and_sources_separate():
    runs = [
        {'run_id': 'pi-1', 'source': 'pi', 'session_id': 'session-a', 'model': 'm',
         'status': 'completed', 'finished_at': '2026-11-02T21:02:00Z',
         'prompt_tokens': 400, 'output_tokens': 40, 'context_tokens': 440,
         'context_limit': 2000, 'eval_duration_s': 4, 'total_duration_s': 6},
        {'run_id': 'pi-2', 'source': 'pi', 'session_id': 'session-a', 'model': 'm',
         'status': 'completed', 'finished_at': '2026-11-02T21:01:00Z',
         'prompt_tokens': 500, 'output_tokens': 60, 'context_tokens': 560,
         'context_limit': 2000, 'eval_duration_s': 6, 'total_duration_s': 8},
        {'run_id': 'web-1', 'source': 'open-webui', 'session_id': 'browser-a',
         'chat_id': 'chat-a', 'message_id': 'message-1', 'model': 'm',
         'status': 'completed', 'finished_at': '2026-11-02T21:00:00Z',
         'prompt_tokens': 100, 'output_tokens': 20, 'context_tokens': 120,
         'context_limit': 1000, 'eval_duration_s': 2, 'total_duration_s': 3},
        {'run_id': 'web-2', 'source': 'open-webui', 'session_id': 'browser-a',
         'chat_id': 'chat-a', 'message_id': 'message-2', 'model': 'm',
         'status': 'completed', 'finished_at': '2026-11-02T20:59:30Z',
         'prompt_tokens': 200, 'output_tokens': 30, 'context_tokens': 230,
         'context_limit': 1000, 'eval_duration_s': 3, 'total_duration_s': 4},
        {'run_id': 'web-other', 'source': 'open-webui', 'session_id': 'browser-a',
         'chat_id': 'chat-b', 'model': 'm', 'status': 'completed',
         'finished_at': '2026-11-02T20:59:00Z'},
        {'run_id': 'single', 'source': 'pi', 'model': 'm', 'status': 'completed',
         'finished_at': '2026-11-02T20:58:00Z'},
    ]
    groups = llmtop_tui.build_history_groups(runs)
    assert [len(group['runs']) for group in groups] == [2, 2, 1, 1]
    assert groups[0]['key'] == ('pi', ('session_id', 'session-a'))
    pi_aggregate = groups[0]['aggregate']
    assert pi_aggregate['prompt_tokens'] == 900
    assert pi_aggregate['output_tokens'] == 100
    assert pi_aggregate['context_tokens'] == 1000
    assert pi_aggregate['context_limit'] == 4000
    assert pi_aggregate['eval_duration_s'] == 10
    assert pi_aggregate['total_duration_s'] == 14
    assert llmtop.token_rate(pi_aggregate) == 10
    assert pi_aggregate['_source_label'] == 'Pi · Session session-'
    assert pi_aggregate['model'] == 'm ×2'
    assert groups[1]['key'] == ('open-webui', ('chat_id', 'chat-a'))
    assert groups[2]['key'] == ('open-webui', ('chat_id', 'chat-b'))
    aggregate = groups[1]['aggregate']
    assert aggregate['prompt_tokens'] == 300
    assert aggregate['output_tokens'] == 50
    assert aggregate['context_tokens'] == 350
    assert aggregate['context_limit'] == 2000
    assert aggregate['eval_duration_s'] == 5
    assert aggregate['total_duration_s'] == 7
    assert llmtop.token_rate(aggregate) == 10
    assert aggregate['_source_label'] == 'WebUI · Chat chat-a'
    assert aggregate['model'] == 'm ×2'
    child = llmtop_tui.indented_history_run(runs[2])
    assert child['_source_label'] == '  Open WebUI'
    assert child['model'] == runs[2]['model']
    assert '_source_label' not in runs[2]
    _, collapsed = llmtop_tui.history_display_items(runs)
    assert [item['kind'] for item in collapsed] == ['group', 'group', 'group', 'run']
    _, expanded = llmtop_tui.history_display_items(runs, expanded={groups[1]['key']})
    assert [item['kind'] for item in expanded] == [
        'group', 'group', 'run', 'run', 'group', 'run']


def test_live_run_keeps_active_run_until_final():
    with tempfile.TemporaryDirectory() as directory:
        live = Path(directory) / 'run.jsonl'
        history = Path(directory) / 'runs.jsonl'
        run = {
            'schema': 2, 'event': 'started', 'run_id': 'active',
            'source': 'open-webui', 'model': 'model',
            'started_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
        assert llmtop.write_live_run(run, live)
        assert len(list(llmtop.load_run_events(live))) == 1
        final = dict(run, event='completed',
                     finished_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                     prompt_tokens=4, output_tokens=6)
        assert llmtop.append_run_history(final, history)
        assert llmtop.write_live_run(final, live)
        displayed = llmtop.load_run_events(live)
        assert len(displayed) == 1
        assert displayed[0]["status"] == "completed"
        assert displayed[0]["prompt_tokens"] == 4
        next_run = dict(run, run_id="next", status="running")
        assert llmtop.write_live_run(next_run, live)
        assert [item["run_id"] for item in llmtop.load_run_events(live)] == ["next", "active"]
        assert len(llmtop.load_run_history(history)) == 1


def test_final_live_runs_expire_but_history_remains():
    with tempfile.TemporaryDirectory() as directory:
        live = Path(directory) / 'run.jsonl'
        history = Path(directory) / 'runs.jsonl'
        old = (datetime.now(timezone.utc).timestamp() - 11)
        stamp = datetime.fromtimestamp(old, timezone.utc).isoformat().replace('+00:00', 'Z')
        final = {'schema': 2, 'event': 'completed', 'run_id': 'done', 'source': 'pi',
                 'model': 'model', 'started_at': stamp, 'updated_at': stamp, 'finished_at': stamp}
        assert llmtop.append_run_history(final, history)
        assert llmtop.write_live_run(final, live)
        assert llmtop.load_run_events(live) == []
        assert live.read_text() == ''
        assert [run['run_id'] for run in llmtop.load_run_history(history)] == ['done']


def test_stale_live_runs_are_pruned():
    with tempfile.TemporaryDirectory() as directory:
        live = Path(directory) / 'run.jsonl'
        run = {
            'schema': 2, 'run_id': 'old', 'source': 'open-webui', 'model': 'model',
            'status': 'running', 'started_at': '2020-01-01T00:00:00Z',
            'updated_at': '2020-01-01T00:00:00Z',
        }
        assert llmtop.write_live_run(run, live)
        assert llmtop.load_run_events(live, max_age=1) == []
        assert live.read_text() == ''


def test_parallel_live_updates_do_not_resurrect_runs():
    with tempfile.TemporaryDirectory() as directory:
        live = Path(directory) / 'run.jsonl'
        barrier = threading.Barrier(12)

        def worker(index):
            run = {'schema': 2, 'run_id': str(index), 'source': 'open-webui',
                   'model': 'model', 'status': 'running',
                   'started_at': '2026-10-31T18:00:00Z'}
            barrier.wait()
            assert llmtop.write_live_run(run, live)
            run.update(event='completed', finished_at='2026-10-31T18:01:00Z')
            assert llmtop.write_live_run(run, live)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        displayed = llmtop.load_run_events(live, max_age=10 ** 9, final_max_age=10 ** 9)
        assert len(displayed) == 1
        assert displayed[0]["status"] == "completed"


def test_pi_events_use_existing_collector_schema():
    import os
    with tempfile.TemporaryDirectory() as directory:
        old_live = os.environ.get('LLMTOP_RUN_FILE')
        old_history = os.environ.get('LLMTOP_RUN_HISTORY_FILE')
        os.environ['LLMTOP_RUN_FILE'] = str(Path(directory) / 'run.jsonl')
        os.environ['LLMTOP_RUN_HISTORY_FILE'] = str(Path(directory) / 'runs.jsonl')
        try:
            started = {'schema': 2, 'event': 'started', 'run_id': 'pi-run',
                       'source': 'pi', 'model': 'model', 'context_limit': 4096,
                       'started_at': '2026-11-01T12:00:00Z'}
            assert llmtop.process_run_event(started)
            assert llmtop.load_run_events(max_age=10 ** 9)[0]['source'] == 'pi'
            completed = dict(started, event='completed', finished_at='2026-11-01T12:00:01Z',
                             prompt_tokens=2, output_tokens=3)
            assert llmtop.process_run_event(completed)
            displayed = llmtop.load_run_events(max_age=10 ** 9, final_max_age=10 ** 9)
            assert displayed[0]['status'] == 'completed'
            assert displayed[0]['prompt_tokens'] == 2
            assert llmtop.load_run_history()[0]['source'] == 'pi'
            assert llmtop.load_run_history()[0]['context_limit'] == 4096
            next_run = dict(started, run_id='pi-next', started_at='2026-11-01T12:00:02Z')
            assert llmtop.process_run_event(next_run)
            assert [item['run_id'] for item in llmtop.load_run_events(
                max_age=10 ** 9, final_max_age=10 ** 9)] == ['pi-next', 'pi-run']
        finally:
            if old_live is None:
                os.environ.pop('LLMTOP_RUN_FILE', None)
            else:
                os.environ['LLMTOP_RUN_FILE'] = old_live
            if old_history is None:
                os.environ.pop('LLMTOP_RUN_HISTORY_FILE', None)
            else:
                os.environ['LLMTOP_RUN_HISTORY_FILE'] = old_history


def test_open_webui_adapter_auto_install():
    original_config = llmtop.open_webui_config
    original_api = llmtop.open_webui_api
    original_install = llmtop.install_open_webui_adapter
    try:
        llmtop.open_webui_config = lambda: ("http://webui", "key", "token")
        llmtop.open_webui_api = lambda *_args: (200, {"is_active": True, "is_global": True,
                                                        "content": Path(llmtop.filter_source_path()).read_text()})
        llmtop.install_open_webui_adapter = lambda: (_ for _ in ()).throw(AssertionError())
        assert llmtop.ensure_open_webui_adapter() == "bereit"

        def missing(*_args):
            raise ValueError("Open-WebUI-API HTTP 404")

        llmtop.open_webui_api = missing
        llmtop.install_open_webui_adapter = lambda: ("installiert", "llmtop_run_metrics")
        assert llmtop.ensure_open_webui_adapter() == "installiert"
    finally:
        llmtop.open_webui_config = original_config
        llmtop.open_webui_api = original_api
        llmtop.install_open_webui_adapter = original_install


def test_tui_draws_loaded_model():
    class Screen:
        def __init__(self):
            self.text = []
            self.calls = []
            self.positions = []

        def getmaxyx(self):
            return 40, 120

        def erase(self):
            pass

        def addstr(self, _y, _x, text, _attr=0):
            self.text.append(text)
            self.calls.append((text, _attr))
            self.positions.append((text, _x))

        def refresh(self):
            pass

    colors = {name: 0 for name in ("structure", "secondary", "model_name",
                                    "context_label", "status_green", "status_yellow",
                                    "rate_green", "rate_yellow", "rate_error", "error",
                                    "offload_good", "offload_mixed", "offload_cpu")}
    colors["model_name"] = 12
    colors["context_label"] = 11
    colors["rate_green"] = 13
    colors["rate_yellow"] = 14
    colors["rate_error"] = 15
    colors["status_green"] = 18
    colors["error"] = 19
    colors["offload_mixed"] = 16
    colors["secondary"] = 17
    state = {"colors": colors, "help": False, "cpu": 10.0,
             "cpu_temp": None, "cpu_temp_source": None,
             "ram": (20.0, 16.0, 12.0), "gpus": [], "gpu_err": None,
             "collector_status": "nicht aktiv", "runs": [{
                 "schema": 2, "run_id": "current", "source": "pi", "model": "model",
                 "status": "running", "context_tokens": 20, "context_limit": 100,
                 "prompt_tokens": 20, "output_tokens": 100, "eval_duration_s": 1,
             }, {
                 "schema": 2, "run_id": "webui", "source": "open-webui", "model": "web-model",
                 "status": "running",
             }], "run_history": [{
                 "schema": 2, "run_id": "history", "source": "pi", "model": "model",
                 "status": "completed", "finished_at": "2030-01-01T00:00:00Z",
                 "prompt_tokens": 2, "output_tokens": 3,
             }], "history_sort": "zeit", "history_desc": True, "history_offset": 0,
             "ollama": {"ok": True, "version": "test", "error": None, "models": [{
                 "name": "model", "size": 100, "size_vram": 50,
                 "context_length": 4096, "expires_at": "2030-01-01T00:00:00Z",
                 "details": {"parameter_size": "1B", "quantization_level": "Q4"},
             }]}}
    screen = Screen()
    llmtop_tui._draw(screen, state, "http://localhost:11434", 2.0)
    assert any(text.startswith("llmtop ") for text in screen.text)
    assert [text for text, x in screen.positions if x == 1][:4] == ["╔══════╗", "║ >▞_  ║", "║  LLM ║", "╚══════╝"]
    assert any(text.startswith("llmtop ") and x == 11 for text, x in screen.positions)
    assert any(text == "LLM Terminal Monitor" and x == 50 for text, x in screen.positions)
    interval_text = "-/+ Intervall 2.0s"
    assert (interval_text, 120 - len(interval_text) - 1) in screen.positions
    assert ("Ollama vtest".ljust(22), 17) in screen.calls
    assert ("verbunden", 18) in screen.calls
    assert ("Open-WebUI Collector".ljust(22), 17) in screen.calls
    assert ("nicht aktiv", 19) in screen.calls
    assert any(text.startswith("── System ") and x == 0 for text, x in screen.positions)
    assert any(text.startswith("CPU") and x == 1 for text, x in screen.positions)
    assert any(text == "1B" and x == 17 for text, x in screen.positions)
    assert any("VRAM/RAM" in text for text in screen.text)
    assert ("   50 %", 16) in screen.calls
    assert ("0 / 0 MiB", 17) in screen.calls
    assert any(text.startswith("Pi · Run current (aktiv 1 · Ergebnis 0)") for text in screen.text)
    assert any(text.startswith("Open WebUI · Run webui (aktiv 1 · Ergebnis 0)") for text in screen.text)
    assert any(text.startswith("Pi        ") for text in screen.text)
    assert any(text.startswith("Open WebUI") for text in screen.text)
    assert ("100.0", 13) in screen.calls
    assert llmtop_tui._rate_color(colors, 9) == 15
    assert llmtop_tui._rate_color(colors, 10) == 14
    assert llmtop_tui._rate_color(colors, 50) == 13
    assert ("model", 12) in screen.calls
    assert ("[##          ]  20%", 18) in screen.calls
    assert (" 100", 17) in screen.calls


if __name__ == '__main__':
    test_run_metric_detail()
    test_run_history_defaults_to_hundred()
    test_clear_run_history()
    test_history_sorting_and_context_cells()
    test_history_groups_keep_all_runs_and_sources_separate()
    test_live_run_keeps_active_run_until_final()
    test_final_live_runs_expire_but_history_remains()
    test_stale_live_runs_are_pruned()
    test_parallel_live_updates_do_not_resurrect_runs()
    test_pi_events_use_existing_collector_schema()
    test_open_webui_adapter_auto_install()
    test_tui_draws_loaded_model()
    print('OK')
