import importlib.util
import json
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location('otop', 'otop.py')
otop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(otop)


def test_run_metric_detail():
    assert otop.run_metric_detail({}) == 'Tokens: warten auf Provider · Tok/s: n/a'
    text = otop.run_metric_detail({'prompt_tokens': 1000, 'output_tokens': 250,
                                   'eval_duration_s': 5})
    assert text == 'Tokens: 1.2k (Prompt 1.0k, Ausgabe 250) · 50.0 Tok/s'
    text = otop.run_metric_detail({'prompt_tokens': 10, 'output_tokens': 3})
    assert text == 'Tokens: 13 (Prompt 10, Ausgabe 3) · Tok/s: n/a'
    assert 'Prompt n/a' in otop.run_metric_detail({'output_tokens': 3})


def test_run_history_defaults_to_ten():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'runs.jsonl'
        records = []
        for index in range(12):
            stamp = f'2026-10-31T18:{index:02d}:00Z'
            records.append({
                'schema': 2, 'run_id': str(index), 'source': 'open-webui',
                'model': 'model', 'status': 'completed',
                'started_at': stamp, 'updated_at': stamp, 'finished_at': stamp,
                'prompt_tokens': index, 'output_tokens': 1,
            })
        path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        result = otop.load_run_history(path)
        assert len(result) == 10
        assert result[0]['run_id'] == '11'
        assert result[-1]['run_id'] == '2'


def test_live_run_keeps_active_run_until_final():
    with tempfile.TemporaryDirectory() as directory:
        live = Path(directory) / 'run.jsonl'
        history = Path(directory) / 'runs.jsonl'
        run = {
            'schema': 2, 'event': 'started', 'run_id': 'active',
            'source': 'open-webui', 'model': 'model',
            'started_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
        assert otop.write_live_run(run, live)
        assert len(list(otop.load_run_events(live))) == 1
        final = dict(run, event='completed', finished_at='2026-10-31T18:01:00Z',
                     prompt_tokens=4, output_tokens=6)
        assert otop.append_run_history(final, history)
        assert otop.write_live_run(final, live)
        assert list(otop.load_run_events(live)) == []
        assert len(otop.load_run_history(history)) == 1


def test_stale_live_runs_are_pruned():
    with tempfile.TemporaryDirectory() as directory:
        live = Path(directory) / 'run.jsonl'
        run = {
            'schema': 2, 'run_id': 'old', 'source': 'open-webui', 'model': 'model',
            'status': 'running', 'started_at': '2020-01-01T00:00:00Z',
            'updated_at': '2020-01-01T00:00:00Z',
        }
        assert otop.write_live_run(run, live)
        assert otop.load_run_events(live, max_age=1) == []
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
            assert otop.write_live_run(run, live)
            run.update(event='completed', finished_at='2026-10-31T18:01:00Z')
            assert otop.write_live_run(run, live)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert otop.load_run_events(live, max_age=10 ** 9) == []


if __name__ == '__main__':
    test_run_metric_detail()
    test_run_history_defaults_to_ten()
    test_live_run_keeps_active_run_until_final()
    test_stale_live_runs_are_pruned()
    test_parallel_live_updates_do_not_resurrect_runs()
    print('OK')
