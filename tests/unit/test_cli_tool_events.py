from sidecar.cli_agent.tool_events import ToolStreamTracker, tool_results_from_message, tool_uses_from_message


def test_tool_uses_from_assistant_message():
    message = {
        "content": [
            {"type": "tool_use", "id": "t1", "name": "vault_read_note", "input": {"file_path": "Notes/a.md"}},
        ]
    }
    events = tool_uses_from_message(message)
    assert len(events) == 1
    assert events[0]["phase"] == "start"
    assert events[0]["tool"] == "vault_read_note"


def test_tool_results_from_user_message():
    message = {
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "hello", "is_error": False},
        ]
    }
    events = tool_results_from_message(message)
    assert len(events) == 1
    assert events[0]["phase"] == "done"
    assert events[0]["result"] == "hello"


def test_stream_tracker_tool_use():
    tracker = ToolStreamTracker()
    start = tracker.handle_stream_event(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "t2", "name": "Read", "input": {}},
        }
    )
    assert start[0]["tool"] == "Read"
    tracker.handle_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{\"file_path\":"}}
    )
    tracker.handle_stream_event(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "\"a.md\"}"}}
    )
    stop = tracker.handle_stream_event({"type": "content_block_stop", "index": 0})
    assert stop[0]["input"] == {"file_path": "a.md"}
    assert tracker.lookup("t2")["input"]["file_path"] == "a.md"
