from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.database as database_module
import backend.graph as graph_module
from backend.database import Base, Player
from backend.graph import (
    _build_knowledge_tracing_prompt,
    _is_repeated_tracing_question,
    _knowledge_tracing_request_directive,
    _parse_verifier_response,
    adapter_node,
    supervisor_node,
    teacher_node,
    verifier_node,
)
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


class _SequentialFakeLLM:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def invoke(self, _messages):
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return _FakeResponse(self._responses[index])


class _FakeNode:
    def __init__(self, node_id: str, label: str, description: str, grade_level: int = 5):
        self.id = node_id
        self.label = label
        self.description = description
        self.grade_level = grade_level


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


def test_parse_verifier_response_strips_quiz_invitation_follow_up():
    is_correct, score_percent, feedback = _parse_verifier_response(
        '{"result": "INCORRECT", "score_percent": 0, "feedback": "That is okay. The point is called an ordered pair. Want another quiz question?"}'
    )

    assert is_correct is False
    assert score_percent == 0
    assert feedback == "[INCORRECT] That is okay. The point is called an ordered pair"


def test_supervisor_routes_active_tracing_answers_to_verifier(monkeypatch):
    def fake_build_llm(state, model, allow_preferred_model=False, priority_enabled=False, **kwargs):
        return _FakeLLM("GENERAL_CHAT"), "fake-model", "platform", None

    monkeypatch.setattr(graph_module, "_build_llm", fake_build_llm)

    state = {
        "session_id": "trace-session",
        "topic": knowledge_tracing_topic_name("Math"),
        "grade_level": "Grade 5",
        "location": "New Hampshire",
        "learning_style": "Visual",
        "username": "teacher-tracer",
        "mastery": 0,
        "current_action": "PROBLEM_GIVEN",
        "last_problem": "What is a unit fraction?",
        "next_dest": "END",
        "role": "Teacher",
        "view_as_student": True,
        "learning_mode": KNOWLEDGE_TRACING_MODE,
        "messages": [HumanMessage(content="don't know")],
    }

    result = supervisor_node(state)

    assert result["next_dest"] == "VERIFIER"


def test_supervisor_routes_tracing_control_message_to_teacher(monkeypatch):
    def fake_build_llm(state, model, allow_preferred_model=False, priority_enabled=False, **kwargs):
        return _FakeLLM("VERIFIER"), "fake-model", "platform", None

    monkeypatch.setattr(graph_module, "_build_llm", fake_build_llm)

    state = {
        "session_id": "trace-session",
        "topic": knowledge_tracing_topic_name("Math"),
        "grade_level": "Grade 5",
        "location": "New Hampshire",
        "learning_style": "Visual",
        "username": "teacher-tracer",
        "mastery": 0,
        "current_action": "PROBLEM_GIVEN",
        "last_problem": "What is a unit fraction?",
        "next_dest": "END",
        "role": "Teacher",
        "view_as_student": True,
        "learning_mode": KNOWLEDGE_TRACING_MODE,
        "messages": [HumanMessage(content="Give me another question on this concept.")],
    }

    result = supervisor_node(state)

    assert result["next_dest"] == "TEACHER"


def test_build_knowledge_tracing_prompt_targets_current_standard_and_recent_variation():
    state = {
        "topic": knowledge_tracing_topic_name("Math"),
        "grade_level": "Grade 5",
        "messages": [
            AIMessage(content="If a point is (5, 3), what is the y-coordinate?"),
            HumanMessage(content="3"),
            AIMessage(content="[CORRECT] Great job!\n\nIf a point is (7, 2), what is the x-coordinate?"),
        ],
        "learning_mode": KNOWLEDGE_TRACING_MODE,
    }
    node = _FakeNode(
        "Geometry->Coordinate_Plane->5.G.3",
        "5.G.3",
        "Understand that attributes belonging to a category of two-dimensional figures also belong to all subcategories of that category.",
    )

    prompt = _build_knowledge_tracing_prompt(state, node, "New Hampshire", "Student Learning Style: Visual. Adapt your explanation accordingly.")

    assert "5.G.3" in prompt
    assert "two-dimensional figures" in prompt
    assert "Do not ask a coordinate-reading or x/y lookup question unless" in prompt
    assert "If a point is (5, 3), what is the y-coordinate?" in prompt
    assert "If a point is (7, 2), what is the x-coordinate?" in prompt


def test_knowledge_tracing_request_directive_requests_different_question_type():
    node = _FakeNode(
        "Geometry->Coordinate_Plane->5.G.3",
        "5.G.3",
        "Understand that attributes belonging to a category of two-dimensional figures also belong to all subcategories of that category.",
    )

    directive = _knowledge_tracing_request_directive("Give me another question on this concept.", node)

    assert "5.G.3" in directive
    assert "different question type" in directive


def test_is_repeated_tracing_question_detects_exact_and_frame_repeats():
    recent = [
        "True or false: Every square is also a rectangle.",
        "If a point is (7, 2), what is the x-coordinate?",
    ]

    assert _is_repeated_tracing_question(
        "True or false: Every square is also a rectangle?",
        recent,
    ) is True
    assert _is_repeated_tracing_question(
        "If a point is (4, 9), what is the x-coordinate?",
        recent,
    ) is True
    assert _is_repeated_tracing_question(
        "Which shape has four equal sides and four right angles?",
        recent,
    ) is False


def test_teacher_knowledge_tracing_retries_repeated_question(monkeypatch):
    testing_session_local = _make_session()
    monkeypatch.setattr(database_module, "SessionLocal", testing_session_local)
    monkeypatch.setattr(graph_module, "SessionLocal", testing_session_local)

    fake_llm = _SequentialFakeLLM(
        [
            "True or false: Every square is also a rectangle.",
            "Which figure is always a rectangle: a square, a triangle, or a pentagon?",
        ]
    )

    def fake_build_llm(state, model, allow_preferred_model=False, priority_enabled=False, **kwargs):
        return fake_llm, "fake-model", "platform", None

    monkeypatch.setattr(graph_module, "_build_llm", fake_build_llm)

    db = testing_session_local()
    player = Player(
        username="repeat-guard",
        display_name="repeat-guard",
        email="repeat-guard@example.com",
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
        "session_id": "repeat-guard-session",
        "topic": knowledge_tracing_topic_name("Math"),
        "grade_level": "Grade 5",
        "location": "New Hampshire",
        "learning_style": "Visual",
        "username": "repeat-guard",
        "mastery": 0,
        "current_action": "PROBLEM_GIVEN",
        "last_problem": "True or false: Every square is also a rectangle.",
        "next_dest": "TEACHER",
        "role": "Teacher",
        "view_as_student": True,
        "learning_mode": KNOWLEDGE_TRACING_MODE,
        "messages": [
            AIMessage(content="True or false: Every square is also a rectangle."),
            HumanMessage(content="true"),
            AIMessage(content="[CORRECT] Nice work."),
            HumanMessage(content="Give me another question on this concept."),
        ],
    }

    result = teacher_node(state)

    assert fake_llm.calls == 2
    assert result["last_problem"] == "Which figure is always a rectangle: a square, a triangle, or a pentagon?"
