import asyncio
import importlib.util
import pathlib


PATH = pathlib.Path(__file__).with_name("llmtop_run_metrics.py")
SPEC = importlib.util.spec_from_file_location("llmtop_filter", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_find_metrics():
    metrics = MODULE.find_metrics({"done": True, "prompt_eval_count": 4, "eval_count": 8,
                                   "eval_duration": 1_000_000_000})
    assert metrics == {"prompt_eval_count": 4, "eval_count": 8,
                       "eval_duration": 1_000_000_000}
    assert MODULE.find_metrics({"usage": {"input_tokens": 2, "output_tokens": 3}}) == {
        "prompt_tokens": 2, "output_tokens": 3}
    assert MODULE.find_metrics({"usage": {"prompt_tokens": 2, "completion_tokens": 3}}) == {
        "prompt_tokens": 2, "output_tokens": 3}
    assert MODULE.find_metrics({"usage": {"completion_tokens": 3, "total_duration": 4}}) == {
        "output_tokens": 3, "total_duration": 4}
    assert MODULE.find_metrics({"usage": {"output_tokens": 3, "response_token/s": 4}}) == {
        "output_tokens": 3, "output_rate": 4}
    # Open WebUI summiert input/output über Tool-Use-Modellaufrufe. Für den
    # Kontext ist der aktuelle Einzelaufruf aus prompt/completion maßgeblich.
    assert MODULE.find_metrics({"usage": {
        "input_tokens": 126382, "output_tokens": 1526,
        "prompt_tokens": 21208, "completion_tokens": 766,
    }}) == {"prompt_tokens": 21208, "output_tokens": 766}


async def exercise():
    adapter = MODULE.Filter()
    sent = []

    async def capture(event):
        sent.append(event)

    adapter._send = capture
    assert adapter._provider({"id": "remote:model", "owned_by": "openai"}) == "openai"
    assert adapter._provider(None) is None
    model = {"id": "qwen:test", "owned_by": "ollama"}
    metadata = {"message_id": "message-1"}
    body = {"model": "qwen:test", "messages": [{"role": "user", "content": "secret"}]}
    await adapter.request(body, metadata, model)
    await adapter.request(body, metadata, model)
    assert sent[0]["event"] == "started"
    assert len([event for event in sent if event["event"] == "started"]) == 1
    assert len(adapter._runs[adapter._key("qwen:test", metadata)]) == 1
    assert "messages" not in sent[0]
    await adapter.stream({"model": "qwen:test", "usage": {
        "prompt_tokens": 2, "completion_tokens": 3, "eval_duration": 1_000_000_000}}, metadata, model)
    assert sent[1]["event"] == "updated"
    assert sent[1]["output_tokens"] == 3
    await adapter.request(body, metadata, model)
    assert len([event for event in sent if event["event"] == "started"]) == 1
    await adapter.stream({"model": "qwen:test", "done": True, "eval_count": 5}, metadata, model)
    assert sent[2]["event"] == "completed"
    assert sent[2]["eval_count"] == 5
    await adapter.outlet({"model": "qwen:test", "messages": []}, metadata, model)
    assert len(sent) == 3

    await adapter.request(body, {"message_id": "a"}, model)
    await adapter.request(body, {"message_id": "b"}, model)
    await adapter.outlet({"model": "qwen:test"}, {"message_id": "a"}, model)
    await adapter.outlet({"model": "qwen:test"}, {"message_id": "b"}, model)
    assert len({event["run_id"] for event in sent if event["event"] == "completed"}) == 3

    starts_before = len([event for event in sent if event["event"] == "started"])
    await adapter.request(body, None, model)
    await adapter.request(body, None, model)
    # Zwei direkte Aufrufe ohne Identität werden im kurzen Debounce-Fenster
    # als derselbe Filterdurchlauf behandelt.
    assert len([event for event in sent if event["event"] == "started"]) == starts_before + 1

    context_adapter = MODULE.Filter()
    context_sent = []

    async def capture_context(event):
        context_sent.append(event)

    context_adapter._send = capture_context
    context_body = {"model": "qwen:test", "messages": [
        {"role": "user", "content": "secret"},
        {"role": "assistant", "usage": {"prompt_tokens": 12, "completion_tokens": 4}},
    ]}
    first_metadata = {"chat_id": "chat-context", "message_id": "context-1"}
    await context_adapter.request(context_body, first_metadata, model)
    assert context_sent[0]["event"] == "started"
    assert "context_tokens" not in context_sent[0]
    assert context_sent[1]["event"] == "updated"
    assert context_sent[1]["context_tokens"] == 16
    assert "messages" not in context_sent[1]
    await context_adapter.stream({"model": "qwen:test", "done": True,
                                  "prompt_eval_count": 20, "eval_count": 5},
                                 first_metadata, model)

    context_sent.clear()
    await context_adapter.request({"model": "qwen:test", "messages": []},
                                  {"chat_id": "chat-context", "message_id": "context-2"}, model)
    assert context_sent[0]["event"] == "started"
    assert context_sent[0]["context_tokens"] == 25
    assert len(context_sent) == 1


if __name__ == "__main__":
    test_find_metrics()
    asyncio.run(exercise())
    print("OK")
