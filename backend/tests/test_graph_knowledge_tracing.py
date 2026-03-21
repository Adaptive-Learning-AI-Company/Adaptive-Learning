from datetime import datetime

from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.database as database_module
import backend.graph as graph_module
from backend.database import Base, Player
from backend.graph import _parse_verifier_response, adapter_node, teacher_node, verifier_node
from backend.knowledge_tracing import KNOWLEDGE_TRACING_MODE, knowledge_tracing_topic_name


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content
        self.usage_metadata = {"input_tokens": 1, "output_tokens": 1}
        self.response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 1}}


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, _messages):
        return _FakeResponse(self._content)


def test_teacher_knowledge_tracing_answer_roundtrip(monkeypatch):
    testing_session_local = _make_session()
    monkeypatch.setattr(database_module, "SessionLocal", testing_session_local)
    monkeypatch.setattr(graph_module, "SessionLocal", testing_session_local)

    captured_calls: list[dict] = []
    responses = iter(
        [
            'What part of speech is the word "but" in the sentence?',
            '{"result": "CORRECT", "score_percent": 100, "feedback": "Correct."}',
            'Which sentence uses "but" to connect two ideas?',
        ]
    )

    def fake_build_llm(state, model, allow_preferred_model=False, priority_enabled=False, **kwargs):
        captured_calls.append({"model": model, "kwargs": kwargs})
        return _FakeLLM(next(responses)), "fake-model", "platform", None

    monkeypatch.setattr(graph_module, "_build_llm", fake_build_llm)

    db = testing_session_local()
    player = Player(
        username="teacher-tracer",
        display_name="teacher-tracer",
        email="teacher-tracer@example.com",
        role="Teacher",
        grade_level=5,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    db.close()

    state = {
        "session_id": "trace-session",
        "topic": knowledge_tracing_topic_name("ELA"),
        "grade_level": "Grade 5",
        "location": "New Hampshire",
        "learning_style": "Visual",
        "username": "teacher-tracer",
        "mastery": 0,
        "current_action": "IDLE",
        "last_problem": "",
        "next_dest": "TEACHER",
        "role": "Teacher",
        "view_as_student": False,
        "learning_mode": KNOWLEDGE_TRACING_MODE,
        "messages": [HumanMessage(content="Quiz me on the next concept.")],
    }

    teacher_result = teacher_node(state)
    assert teacher_result["last_problem"] == 'What part of speech is the word "but" in the sentence?'
    answer_state = dict(state)
    answer_state.update({key: value for key, value in teacher_result.items() if key != "messages"})
    answer_state["messages"] = state["messages"] + teacher_result["messages"] + [HumanMessage(content="conjunction")]

    verifier_result = verifier_node(answer_state)
    adapter_state = dict(answer_state)
    adapter_state.update({key: value for key, value in verifier_result.items() if key != "messages"})
    adapter_state["messages"] = answer_state["messages"] + verifier_result["messages"]
    adapter_result = adapter_node(adapter_state)

    assert teacher_result["current_action"] == "PROBLEM_GIVEN"
    assert verifier_result["next_dest"] == "ADAPTER"
    assert adapter_result["next_dest"] == "END"
    assert adapter_result["current_action"] == "PROBLEM_GIVEN"
    assert adapter_result["mastery"]["unit"] >= 0.0
    assert adapter_result["last_problem"] == 'Which sentence uses "but" to connect two ideas?'
    assert len(adapter_result["messages"]) == 1
    assert adapter_result["messages"][0].content == "[CORRECT] Correct.\n\nWhich sentence uses \"but\" to connect two ideas?"

    assert len(captured_calls) == 3
    assert "model_kwargs" not in captured_calls[0]["kwargs"]
    assert "model_kwargs" not in captured_calls[1]["kwargs"]
    assert "model_kwargs" not in captured_calls[2]["kwargs"]


def test_parse_verifier_response_strips_rogue_follow_up_question():
    is_correct, score_percent, feedback = _parse_verifier_response(
        '{"result": "CORRECT", "score_percent": 100, "feedback": "Correct. Next concept: What is the function of chlorophyll in plants?"}'
    )

    assert is_correct is True
    assert score_percent == 100
    assert feedback == "[CORRECT] Correct"
