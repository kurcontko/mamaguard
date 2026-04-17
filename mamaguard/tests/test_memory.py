"""Unit tests for mamaguard.shared.memory (FHIR-native agent memory)."""

import base64
import unittest
from unittest.mock import MagicMock, patch

from mamaguard.shared import memory


def _make_doc_ref(content_markdown: str, date: str = "2026-04-10T10:00:00Z",
                  memory_type: str = "trajectory",
                  resource_id: str = "docref-1") -> dict:
    return {
        "resourceType": "DocumentReference",
        "id": resource_id,
        "date": date,
        "type": {"coding": [{
            "system": memory.FHIR_MEMORY_SYSTEM,
            "code": memory.FHIR_MEMORY_CODE,
        }]},
        "category": [{"coding": [{
            "system": memory.FHIR_MEMORY_SYSTEM,
            "code": memory_type,
        }]}],
        "content": [{"attachment": {
            "contentType": "text/markdown",
            "data": base64.b64encode(content_markdown.encode("utf-8")).decode("ascii"),
        }}],
    }


class TestFetchAgentMemory(unittest.TestCase):

    def test_missing_context_returns_empty(self):
        self.assertEqual(memory.fetch_agent_memory("", "", ""), [])

    @patch("mamaguard.shared.memory.httpx.get")
    def test_parses_bundle(self, mock_get):
        bundle = {"entry": [
            {"resource": _make_doc_ref("BP trending up", resource_id="r1")},
            {"resource": _make_doc_ref("Housing referral open", resource_id="r2",
                                       memory_type="plan")},
        ]}
        resp = MagicMock()
        resp.json.return_value = bundle
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        notes = memory.fetch_agent_memory("https://f", "tok", "p1")
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0].content, "BP trending up")
        self.assertEqual(notes[0].resource_id, "r1")
        self.assertEqual(notes[1].memory_type, "plan")

    @patch("mamaguard.shared.memory.httpx.get")
    def test_ignores_foreign_document_references(self, mock_get):
        foreign = {
            "resourceType": "DocumentReference",
            "id": "other",
            "type": {"coding": [{"system": "other-system", "code": "foo"}]},
            "content": [{"attachment": {"data": base64.b64encode(
                b"not ours").decode("ascii")}}],
        }
        bundle = {"entry": [{"resource": foreign}]}
        resp = MagicMock()
        resp.json.return_value = bundle
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        self.assertEqual(memory.fetch_agent_memory("https://f", "tok", "p1"), [])

    @patch("mamaguard.shared.memory.httpx.get")
    def test_fhir_error_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("network down")
        self.assertEqual(memory.fetch_agent_memory("https://f", "tok", "p1"), [])


class TestWriteAgentMemory(unittest.TestCase):

    @patch("mamaguard.shared.memory.httpx.post")
    def test_posts_document_reference(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {"id": "new-123"}
        resp.raise_for_status = MagicMock()
        mock_post.return_value = resp

        result = memory.write_agent_memory(
            "https://f", "tok", "p1",
            content_markdown="**Template** — Risk: URGENT",
            memory_type="trajectory-elevated",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["resource_id"], "new-123")

        call = mock_post.call_args
        body = call.kwargs["json"]
        self.assertEqual(body["resourceType"], "DocumentReference")
        self.assertEqual(body["subject"]["reference"], "Patient/p1")
        attachment = body["content"][0]["attachment"]
        decoded = base64.b64decode(attachment["data"]).decode("utf-8")
        self.assertIn("URGENT", decoded)

    def test_empty_content_skipped(self):
        result = memory.write_agent_memory("https://f", "tok", "p1", "   ")
        self.assertEqual(result["status"], "skipped")


class TestDeriveAndInject(unittest.TestCase):

    def test_derive_extracts_talk_and_template(self):
        response = (
            "prefix\n\n**Talk** — Maria has urgent findings.\n\n"
            "**Template** — Risk Level: URGENT\nBP high.\n\n"
            "**Table**\n|a|b|\n|-|-|\n\n**Task**\n1. call clinician\n"
        )
        note = memory._derive_memory_note(response)
        self.assertIn("**Talk**", note)
        self.assertIn("**Template**", note)
        self.assertNotIn("**Table**", note)
        self.assertNotIn("**Task**", note)

    def test_derive_returns_empty_when_no_template(self):
        self.assertEqual(memory._derive_memory_note("no 5t here"), "")

    def test_classify_elevated(self):
        self.assertEqual(
            memory._classify_memory("Risk Level: URGENT"),
            "trajectory-elevated",
        )
        self.assertEqual(
            memory._classify_memory("Routine follow-up"),
            "trajectory",
        )

    def test_format_memory_block_empty(self):
        self.assertEqual(memory.format_memory_block([]), "")

    def test_format_memory_block_renders_markdown(self):
        notes = [memory.MemoryNote(
            date="2026-04-01T10:00:00Z",
            memory_type="trajectory",
            content="BP rising",
        )]
        block = memory.format_memory_block(notes)
        self.assertIn("<patient-memory>", block)
        self.assertIn("BP rising", block)
        self.assertIn("2026-04-01", block)


class _FakeConfig:
    def __init__(self, system_instruction=None):
        self.system_instruction = system_instruction


class _FakeLlmRequest:
    def __init__(self, system_instruction=None):
        self.config = _FakeConfig(system_instruction)


class _FakeState(dict):
    pass


class _FakeCallbackContext:
    def __init__(self, state, invocation_id=""):
        self.state = state
        self.invocation_id = invocation_id


class TestInjectAndPersistCallbacks(unittest.TestCase):

    @patch("mamaguard.shared.memory.fetch_agent_memory")
    def test_inject_appends_to_system_instruction(self, mock_fetch):
        mock_fetch.return_value = [memory.MemoryNote(
            date="2026-04-01", memory_type="trajectory", content="BP rising",
        )]
        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })
        ctx = _FakeCallbackContext(state)
        req = _FakeLlmRequest(system_instruction="you are MamaGuard")

        memory.inject_memory_block(ctx, req)
        self.assertIn("<patient-memory>", req.config.system_instruction)
        self.assertIn("BP rising", req.config.system_instruction)
        # Dedupe key encodes both invocation + patient; test context has no
        # invocation_id so the fallback is just the patient id.
        self.assertEqual(state["_memory_injected_for"], "p1")

    @patch("mamaguard.shared.memory.fetch_agent_memory")
    def test_inject_idempotent_per_patient(self, mock_fetch):
        mock_fetch.return_value = [memory.MemoryNote(
            date="2026-04-01", memory_type="trajectory", content="x",
        )]
        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })
        ctx = _FakeCallbackContext(state)
        req = _FakeLlmRequest(system_instruction="base")

        memory.inject_memory_block(ctx, req)
        first = req.config.system_instruction
        memory.inject_memory_block(ctx, req)
        self.assertEqual(first, req.config.system_instruction)
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("mamaguard.shared.memory.write_agent_memory")
    def test_persist_skips_when_tool_call_pending(self, mock_write):
        part = MagicMock(function_call=MagicMock(), text=None)
        content = MagicMock(parts=[part])
        response = MagicMock(content=content)

        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })
        memory.persist_memory_note(_FakeCallbackContext(state), response)
        mock_write.assert_not_called()

    @patch("mamaguard.shared.memory.write_agent_memory")
    def test_persist_writes_terminal_response(self, mock_write):
        mock_write.return_value = {"status": "success", "resource_id": "r1",
                                    "memory_type": "trajectory"}
        part = MagicMock(function_call=None, thought=False,
                        text="**Talk** — summary.\n\n**Template** — Risk: URGENT\n")
        content = MagicMock(parts=[part])
        response = MagicMock(content=content)

        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })
        memory.persist_memory_note(_FakeCallbackContext(state), response)
        mock_write.assert_called_once()
        kwargs = mock_write.call_args.kwargs
        self.assertIn("URGENT", kwargs["content_markdown"])
        self.assertEqual(kwargs["memory_type"], "trajectory-elevated")

    @patch("mamaguard.shared.memory.write_agent_memory")
    def test_persist_skips_without_template(self, mock_write):
        part = MagicMock(function_call=None, thought=False,
                        text="just chatter, no template")
        content = MagicMock(parts=[part])
        response = MagicMock(content=content)

        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })
        memory.persist_memory_note(_FakeCallbackContext(state), response)
        mock_write.assert_not_called()


class TestMultiTurnLifecycle(unittest.TestCase):
    """
    Guard against regressions where memory stops working after the first
    turn of a session — the original bug was that the dedupe flag was
    keyed on patient_id alone, which is stable across turns.
    """

    @patch("mamaguard.shared.memory.fetch_agent_memory")
    def test_inject_refetches_each_turn(self, mock_fetch):
        mock_fetch.return_value = [memory.MemoryNote(
            date="2026-04-01", memory_type="trajectory", content="x",
        )]
        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })

        # Turn 1 — fresh invocation_id, fetch is called.
        memory.inject_memory_block(
            _FakeCallbackContext(state, invocation_id="inv-1"),
            _FakeLlmRequest(system_instruction="s"),
        )
        # Second LLM hop inside turn 1 — same invocation_id, no refetch.
        memory.inject_memory_block(
            _FakeCallbackContext(state, invocation_id="inv-1"),
            _FakeLlmRequest(system_instruction="s"),
        )
        # Turn 2 — new invocation_id, must refetch so end-of-turn-1 notes
        # are visible to the LLM at start of turn 2.
        memory.inject_memory_block(
            _FakeCallbackContext(state, invocation_id="inv-2"),
            _FakeLlmRequest(system_instruction="s"),
        )
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("mamaguard.shared.memory.write_agent_memory")
    def test_persist_writes_every_turn(self, mock_write):
        mock_write.return_value = {"status": "success", "resource_id": "r",
                                    "memory_type": "trajectory"}

        def _terminal_response():
            part = MagicMock(function_call=None, thought=False,
                            text="**Talk** — t.\n\n**Template** — Risk: URGENT\n")
            content = MagicMock(parts=[part])
            return MagicMock(content=content)

        state = _FakeState({
            "fhir_url": "https://f", "fhir_token": "t", "patient_id": "p1",
        })

        memory.persist_memory_note(
            _FakeCallbackContext(state, invocation_id="inv-1"),
            _terminal_response(),
        )
        memory.persist_memory_note(
            _FakeCallbackContext(state, invocation_id="inv-1"),
            _terminal_response(),
        )
        memory.persist_memory_note(
            _FakeCallbackContext(state, invocation_id="inv-2"),
            _terminal_response(),
        )
        self.assertEqual(mock_write.call_count, 2)


if __name__ == "__main__":
    unittest.main()
