
import operator
import os
import re
import time
from typing import TypedDict, List, Annotated, Union
from fastapi import HTTPException
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, END
from .prompts import TEACHER_PROMPT, TEACHER_OF_TEACHERS_PROMPT, PROBLEM_GENERATOR_PROMPT, VERIFIER_PROMPT, SUPERVISOR_PROMPT, ADAPTER_PROMPT
from .database import log_interaction, get_db, Player, StudentNodeProgress, TopicProgress, SessionLocal
from .knowledge_graph import get_graph, get_all_subjects_stats
from .knowledge_tracing import (
    KNOWLEDGE_TRACING_MODE,
    apply_tracing_result,
    get_topic_progress,
    is_knowledge_tracing_mode,
    learning_mode_label,
    normalize_learning_mode,
    refresh_tracing_topic_mastery,
    select_next_teach_me_node,
    select_next_tracing_node,
    topic_label_for_mode,
)
from .config import load_local_env
from .billing import PRIORITY_SERVICE_TIER, get_hosted_model_selection, get_hosted_priority_selection, get_model_provider, model_supports_priority
from .profile_security import decrypt_profile_secret
from .student_tracking import mark_node_mastered, record_answer_evaluation, touch_current_node
import json 

load_local_env()

# State Definition
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    session_id: str
    topic: str
    grade_level: str
    location: str
    learning_style: str
    username: str
    mastery: int
    current_action: str
    last_problem: str
    next_dest: str
    role: str # "Student" or "Teacher"
    view_as_student: bool
    learning_mode: str

def _is_teacher_role(role: str | None) -> bool:
    normalized = (role or "").strip()
    return normalized in {"Teacher", "Admin"}


def _hosted_teacher_model() -> str:
    return get_hosted_model_selection()[0]


def _hosted_verifier_model() -> str:
    return get_hosted_model_selection()[1]


def _hosted_fast_model() -> str:
    return get_hosted_model_selection()[2]


def _hosted_teacher_priority_enabled() -> bool:
    return get_hosted_priority_selection()[0]


def _hosted_verifier_priority_enabled() -> bool:
    return get_hosted_priority_selection()[1]


def _hosted_fast_priority_enabled() -> bool:
    return get_hosted_priority_selection()[2]


def _platform_api_key_for_model(model_name: str) -> str | None:
    provider = get_model_provider(model_name)
    if provider == "google":
        return os.getenv("GOOGLE_API_KEY")
    return os.getenv("OPENAI_API_KEY")


def _build_llm(state: AgentState, model: str, allow_preferred_model: bool = False, priority_enabled: bool = False, **kwargs):
    username = state.get("username") if state else None
    api_key, resolved_model, billing_source = _resolve_llm_settings_for_user(
        username,
        requested_model=model,
        allow_preferred_model=allow_preferred_model,
    )
    provider = get_model_provider(resolved_model)
    model_kwargs = dict(kwargs)
    service_tier = None
    if priority_enabled and billing_source == "platform" and provider == "openai" and model_supports_priority(resolved_model):
        service_tier = PRIORITY_SERVICE_TIER
    if provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Gemini support is not installed on the server.") from exc

        if not api_key:
            raise HTTPException(status_code=503, detail="GOOGLE_API_KEY is not configured on the server.")

        gemini_response_mime = None
        if "model_kwargs" in model_kwargs and isinstance(model_kwargs["model_kwargs"], dict):
            response_format = model_kwargs["model_kwargs"].get("response_format", {})
            if isinstance(response_format, dict) and response_format.get("type") == "json_object":
                gemini_response_mime = "application/json"
            model_kwargs.pop("model_kwargs", None)
        if gemini_response_mime:
            model_kwargs["response_mime_type"] = gemini_response_mime
        return ChatGoogleGenerativeAI(model=resolved_model, google_api_key=api_key, **model_kwargs), resolved_model, billing_source, None

    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured on the server.")
    if service_tier:
        model_kwargs["service_tier"] = service_tier
    return ChatOpenAI(model=resolved_model, api_key=api_key, **model_kwargs), resolved_model, billing_source, service_tier


def _resolve_llm_settings_for_user(
    username: str | None,
    requested_model: str,
    allow_preferred_model: bool = False,
) -> tuple[str | None, str, str]:
    resolved_model = requested_model
    if not username:
        return _platform_api_key_for_model(resolved_model), resolved_model, "platform"

    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == username).first()
        if player:
            if player.openai_api_key_encrypted:
                if allow_preferred_model and player.preferred_model:
                    preferred_candidate = player.preferred_model.strip()
                    if preferred_candidate and get_model_provider(preferred_candidate) == "openai":
                        resolved_model = preferred_candidate
                decrypted = decrypt_profile_secret(player.openai_api_key_encrypted)
                if decrypted:
                    return decrypted, resolved_model, "personal"
    finally:
        db.close()

    return _platform_api_key_for_model(resolved_model), resolved_model, "platform"


def _subject_key_for_topic(topic_name: str | None) -> str:
    if not topic_name:
        return "General"

    token = topic_name.strip().split(" ")[0].replace("-", "_")
    normalized = token.lower()
    subject_map = {
        "math": "Math",
        "science": "Science",
        "history": "Social_Studies",
        "social_studies": "Social_Studies",
        "socialstudies": "Social_Studies",
        "english": "ELA",
        "ela": "ELA",
    }
    return subject_map.get(normalized, token)


def _current_node_id_for_state(state: AgentState) -> str | None:
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == state.get("username")).first()
        if not player:
            return None

        progress = get_topic_progress(
            db,
            player.id,
            state.get("topic"),
            _learning_mode(state),
        )
        if not progress:
            return None

        return progress.current_node
    finally:
        db.close()


def _extract_usage_metrics(message) -> tuple[int | None, int | None]:
    if message is None:
        return None, None

    usage = getattr(message, "usage_metadata", None) or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")

    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage", {})
    if input_tokens is None:
        input_tokens = token_usage.get("prompt_tokens")
    if output_tokens is None:
        output_tokens = token_usage.get("completion_tokens")

    return input_tokens, output_tokens


def _normalize_score_percent(value, fallback: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = fallback
    return max(0, min(score, 100))


def _parse_verifier_response(raw_content: str) -> tuple[bool, int, str]:
    fallback_is_correct = "[CORRECT]" in raw_content.upper() and "[INCORRECT]" not in raw_content.upper()
    fallback_score = 100 if fallback_is_correct else 0
    feedback = raw_content.strip()

    try:
        parsed = json.loads(raw_content)
        result = str(parsed.get("result", "")).strip().upper()
        is_correct = result == "CORRECT"
        if result not in {"CORRECT", "INCORRECT"}:
            is_correct = fallback_is_correct
        score_percent = _normalize_score_percent(parsed.get("score_percent"), 100 if is_correct else fallback_score)
        feedback = str(parsed.get("feedback", "")).strip() or feedback
    except Exception:
        is_correct = fallback_is_correct
        score_percent = fallback_score

    token = "[CORRECT]" if is_correct else "[INCORRECT]"
    if token not in feedback:
        feedback = token + " " + feedback
    return is_correct, score_percent, _strip_feedback_follow_up_question(feedback)


def _strip_feedback_follow_up_question(feedback: str) -> str:
    cleaned = " ".join(str(feedback or "").split()).strip()
    if cleaned == "":
        return cleaned

    lowered = cleaned.lower()
    for marker in (
        "next concept:",
        "next question:",
        "follow-up:",
        "another check:",
        "next checkpoint:",
        "want another quiz question",
        "want another question",
        "would you like another question",
        "would you like another quiz question",
        "ready for another question",
    ):
        marker_index = lowered.find(marker)
        if marker_index > 0:
            return cleaned[:marker_index].rstrip(" \t\r\n-:;,.")

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    if len(sentences) > 1 and sentences[-1].endswith("?"):
        preserved = " ".join(sentences[:-1]).strip()
        if preserved:
            return preserved

    return cleaned


def _normalized_message_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _knowledge_tracing_route_override(state: AgentState, last_user_msg: str) -> str | None:
    if not is_knowledge_tracing_mode(_learning_mode(state)):
        return None

    normalized = _normalized_message_text(last_user_msg)
    if normalized.startswith("[system] update grade level context"):
        return "TEACHER"
    if normalized.startswith("[system] update role context"):
        return "TEACHER"

    for prefix in (
        "quiz me on the next concept",
        "give me another question on this concept",
        "challenge me with a slightly harder question on this concept",
        "ask the next assessment question for the current concept",
    ):
        if normalized.startswith(prefix):
            return "TEACHER"

    if state.get("current_action") == "PROBLEM_GIVEN":
        return "VERIFIER"
    return None


def _extract_question_sentences(text: str | None) -> list[str]:
    cleaned = " ".join(str(text or "").split()).strip()
    if cleaned == "":
        return []

    questions: list[str] = []
    for match in re.findall(r"[^?]*\?", cleaned):
        candidate = match.strip()
        if candidate and candidate not in questions:
            questions.append(candidate)
    return questions


def _recent_tracing_questions(state: AgentState, limit: int = 3) -> list[str]:
    collected: list[str] = []
    for message in reversed(state.get("messages", [])):
        for question in reversed(_extract_question_sentences(getattr(message, "content", ""))):
            if question not in collected:
                collected.append(question)
            if len(collected) >= limit:
                return list(reversed(collected))
    return list(reversed(collected))


def _knowledge_tracing_request_directive(last_content: str, current_node) -> str:
    concept_label = current_node.label if current_node else "this concept"
    normalized = _normalized_message_text(last_content)

    if normalized.startswith("challenge me with a slightly harder question on this concept"):
        return (
            f"Ask one slightly harder assessment question about '{concept_label}'. "
            "Use a different question type from the recent tracer questions."
        )
    if normalized.startswith("give me another question on this concept"):
        return (
            f"Ask one new assessment question about '{concept_label}'. "
            "Use a different question type from the recent tracer questions."
        )
    if normalized.startswith("quiz me on the next concept") or normalized.startswith(
        "ask the next assessment question for the current concept"
    ):
        return (
            f"Ask one assessment question that directly tests '{concept_label}'. "
            "If this is a new concept, reset the content to match the current concept instead of the previous one."
        )
    return f"Ask one assessment question that directly tests '{concept_label}'."


def _build_knowledge_tracing_prompt(state: AgentState, current_node, loc: str, style_instruction: str) -> str:
    subject_label = topic_label_for_mode(str(state.get("topic", "General")), _learning_mode(state))
    concept_label = current_node.label if current_node else "core concepts overview"
    concept_id = current_node.id if current_node else str(state.get("topic", "unknown"))
    concept_description = current_node.description if current_node and current_node.description else "No description provided."
    recent_questions = _recent_tracing_questions(state, limit=3)
    recent_questions_block = "\n".join(f"- {question}" for question in recent_questions) if recent_questions else "- none yet"

    return (
        "You are an Adaptive Knowledge Tracer.\n"
        f"Subject: {subject_label}\n"
        f"Current standard or concept code: {concept_label}\n"
        f"Knowledge-graph node id: {concept_id}\n"
        f"Current concept description: {concept_description}\n"
        f"Grade Level: {state['grade_level']}\n"
        f"Location Context: {loc}.\n"
        f"{style_instruction.strip()}\n"
        "Ask exactly one concise assessment question about the CURRENT concept only.\n"
        "The question must directly assess the current concept description, not the previous concept from the conversation.\n"
        "If the concept changed, reset the content immediately to match the new concept.\n"
        "Do not teach the lesson first.\n"
        "Do not reveal the answer.\n"
        "Do not ask whether the student wants another question.\n"
        "Keep the question standalone, student-facing, and short.\n"
        "Avoid repeating the same question frame, sentence template, or cognitive action as the recent tracer questions below.\n"
        "Prefer a different format when possible: classify an example, identify a property, compare two cases, choose the best example, interpret a short scenario, or true/false with justification.\n"
        "Do not ask a coordinate-reading or x/y lookup question unless the CURRENT concept description explicitly mentions axes, coordinates, ordered pairs, graphing points, or the coordinate plane.\n"
        f"Recent tracer questions to avoid repeating:\n{recent_questions_block}\n"
        "Output only the next student-facing question."
    )


def _parse_target_grade(state: AgentState) -> int | None:
    try:
        grade_value = state.get("grade_level", "")
        if isinstance(grade_value, int):
            return grade_value
        if "Grade" in str(grade_value):
            import re

            match = re.search(r"\d+", str(grade_value))
            if match:
                return int(match.group())
        return int(grade_value)
    except Exception:
        return None


def _learning_mode(state: AgentState) -> str:
    return normalize_learning_mode(state.get("learning_mode"))


def _select_active_node(db, player: Player, state: AgentState):
    target_grade = _parse_target_grade(state)
    topic_name = state.get("topic")
    learning_mode = _learning_mode(state)
    kg = get_graph(topic_name)
    progress = get_topic_progress(db, player.id, topic_name, learning_mode)
    current_node_id = progress.current_node if progress else None

    if is_knowledge_tracing_mode(learning_mode):
        return select_next_tracing_node(
            db,
            player_id=player.id,
            topic_name=topic_name,
            target_grade=target_grade,
            current_node_id=current_node_id,
        )

    if progress and current_node_id:
        current_node = kg.get_node(current_node_id)
        if current_node is not None:
            last_msg = state["messages"][-1].content if state.get("messages") else ""
            is_override_trigger = "[System] Update Grade Level Context" in last_msg
            if target_grade is not None:
                if is_override_trigger and current_node.grade_level == target_grade:
                    return current_node
                if not is_override_trigger and int(progress.mastery_score or 0) > 0:
                    return current_node
                if abs(int(current_node.grade_level or 0) - int(target_grade)) <= 1:
                    return current_node

    current_node = select_next_teach_me_node(
        db,
        player_id=player.id,
        topic_name=topic_name,
        target_grade=target_grade,
        current_node_id=current_node_id,
    )
    if current_node is None and progress and progress.current_node:
        return get_graph(topic_name).get_node(progress.current_node)
    return current_node

# Nodes
def supervisor_node(state: AgentState):
    messages = state['messages']
    last_user_msg = messages[-1].content

    tracing_override = _knowledge_tracing_route_override(state, last_user_msg)
    if tracing_override is not None:
        return {"next_dest": tracing_override}
    
    # Simple logic mapping for robust routing
    prompt = SUPERVISOR_PROMPT.format(
        last_message=last_user_msg,
        last_action=state.get('current_action', 'IDLE')
    )
    
    decision_llm, _decision_model, _decision_billing_source, _decision_service_tier = _build_llm(
        state,
        _hosted_fast_model(),
        priority_enabled=_hosted_fast_priority_enabled(),
        temperature=0,
    )
    response = decision_llm.invoke(prompt)
    decision = response.content.strip().upper()
    
    # Fallback
    valid_dests = ["VERIFIER", "TEACHER", "PROBLEM_GENERATOR", "GENERAL_CHAT"]
    found = False
    for v in valid_dests:
        if v in decision:
            decision = v
            found = True
            break
    if not found:
        decision = "GENERAL_CHAT"
        
    return {"next_dest": decision}

def teacher_node(state: AgentState):
    loc = state.get("location", "New Hampshire")
    style = state.get("learning_style", "Universal")
    style_instruction = f"\nStudent Learning Style: {style}. Adapt your explanation accordingly."
    target_grade = _parse_target_grade(state)
    learning_mode = _learning_mode(state)
    kg = get_graph(state["topic"])
    current_node = None

    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == state["username"]).first()
        if player:
            current_node = _select_active_node(db, player, state)
            if current_node:
                touch_current_node(
                    db,
                    player,
                    state["topic"],
                    current_node.id,
                    learning_mode=learning_mode,
                )
                db.commit()
    finally:
        db.close()

    topic_label = topic_label_for_mode(str(state.get("topic", "General")), learning_mode)
    if current_node:
        var_desc = f" ({current_node.description})" if current_node.description else ""
        topic_label = f"{topic_label}: {current_node.label}{var_desc}"
    else:
        topic_label = f"{topic_label}: core concepts overview"

    role = state.get("role", "Student")
    view_as_student = state.get("view_as_student", False)
    prompt = ""
    if is_knowledge_tracing_mode(learning_mode):
        prompt = _build_knowledge_tracing_prompt(state, current_node, loc, style_instruction)
    elif _is_teacher_role(role) and not view_as_student:
        print("[AGENTS] Using TEACHER_OF_TEACHERS prompt")

        teacher_grade = state["grade_level"]
        db_local = SessionLocal()
        try:
            p = db_local.query(Player).filter(Player.username == state["username"]).first()
            if p:
                profile_grade = p.grade_level
                content_grade = state["grade_level"]
                if str(profile_grade) in str(content_grade):
                    teacher_grade = f"Grade {profile_grade}"
                else:
                    teacher_grade = f"Grade {profile_grade} (Teaching {content_grade} Content)"
        finally:
            db_local.close()

        prompt = TEACHER_OF_TEACHERS_PROMPT.format(
            topic=topic_label,
            grade_level=teacher_grade,
            location=loc,
        )
    else:
        prompt = TEACHER_PROMPT.format(
            topic=topic_label,
            grade_level=state["grade_level"],
            location=loc,
            mastery=state.get("mastery", 0),
        ) + style_instruction

    print(f"\n[AGENTS] TEACHER NODE\nPROMPT:\n{prompt}\n")

    context_msgs = list(state['messages'])
    if context_msgs:
        last_content = context_msgs[-1].content
        if is_knowledge_tracing_mode(learning_mode):
            if "[System] Update Grade Level Context" in last_content:
                directive = (
                    f"Knowledge tracing context updated to {state['grade_level']}. "
                    f"Ask one assessment question that directly tests '{current_node.label if current_node else 'this topic'}'."
                )
            elif "[System] Update Role Context" in last_content:
                directive = (
                    f"Role context updated. Continue adaptive testing on '{current_node.label if current_node else 'this topic'}'."
                )
            else:
                directive = _knowledge_tracing_request_directive(last_content, current_node)
            context_msgs = [HumanMessage(content=directive)]
            print(f"[AGENTS] Replaced Tracing Context with Directive: {directive}")
        elif "[System] Update Grade Level Context" in last_content:
            directive = f"Context Updated to {state['grade_level']}. Topic switched to '{current_node.label if current_node else 'New Topic'}'. Please provide the Teaching Guide for '{current_node.label if current_node else 'this topic'}' immediately."
            context_msgs[-1] = HumanMessage(content=directive)
            print(f"[AGENTS] Replaced Trigger with Directive: {directive}")
            
        elif "[System] Update Role Context" in last_content:
            if _is_teacher_role(role) and not view_as_student:
                directive = f"Role Switched to Teacher View. The user is a colleague. Provide a Teaching Guide for '{current_node.label if current_node else 'this topic'}' immediately."
            else:
                directive = f"Role Switched to Student View. The user is a student (Grade {state['grade_level']}). Introduce the topic '{current_node.label if current_node else 'New Topic'}' in a fun way and ask a checking question."
            context_msgs[-1] = HumanMessage(content=directive)
            print(f"[AGENTS] Replaced Role Trigger with Directive: {directive}")

    messages = [SystemMessage(content=prompt)] + context_msgs
    teacher_llm, teacher_model_name, teacher_billing_source, teacher_service_tier = _build_llm(
        state,
        _hosted_teacher_model(),
        allow_preferred_model=True,
        priority_enabled=_hosted_teacher_priority_enabled(),
    )
    start_time = time.perf_counter()
    response = teacher_llm.invoke(messages)
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    input_tokens, output_tokens = _extract_usage_metrics(response)
    print(f"RESPONSE:\n{response.content}\n")
    
    log_interaction(
        username=state.get("username", "Unknown"),
        subject=_subject_key_for_topic(state.get("topic")),
        user_query=state['messages'][-1].content if state['messages'] else "",
        agent_response=response.content,
        source_node="teacher",
        session_id=state.get("session_id"),
        topic_name=state.get("topic"),
        node_id=current_node.id if current_node else _current_node_id_for_state(state),
        model_name=teacher_model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        billing_source=teacher_billing_source,
        service_tier=teacher_service_tier,
        event_type="knowledge_trace_question" if is_knowledge_tracing_mode(learning_mode) else "teacher_explanation",
    )

    done_unit, total_unit = 0, 0
    done_subj, total_subj = 0, 0
    done_grade, total_grade = 0, 0

    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == state["username"]).first()
        if player:
            if is_knowledge_tracing_mode(learning_mode):
                refresh = refresh_tracing_topic_mastery(db, player.id, state["topic"], target_grade)
                done_subj = refresh["subject_score"]
                total_subj = 100
                if current_node:
                    current_row = db.query(StudentNodeProgress).filter(
                        StudentNodeProgress.player_id == player.id,
                        StudentNodeProgress.topic_name == state["topic"],
                        StudentNodeProgress.node_id == current_node.id,
                        StudentNodeProgress.learning_mode == KNOWLEDGE_TRACING_MODE,
                    ).first()
                    done_unit = int(current_row.mastery_level or 0) * 10 if current_row else 0
                    total_unit = 100
            else:
                prog = get_topic_progress(db, player.id, state["topic"], learning_mode)
                if prog and prog.completed_nodes:
                    subtree_root = None
                    reference_node = current_node.id if current_node else prog.completed_nodes[-1]
                    if reference_node and "->" in reference_node:
                        parts = reference_node.split("->")
                        subtree_root = "->".join(parts[:-1]) if len(parts) > 1 else parts[0]
                    done_unit, total_unit = kg.get_completion_stats(prog.completed_nodes, subtree_root)
                    done_subj, total_subj = kg.get_completion_stats(prog.completed_nodes)
            done_grade, total_grade = get_all_subjects_stats(player.id, db)
    except Exception as e:
        print(f"[TEACHER DEBUG] Error calculating mastery: {e}")
    finally:
        db.close()

    mastery_data = {
        "unit": 0.0,
        "subject": 0.0,
        "grade": 0.0
    }

    if total_unit > 0:
        mastery_data["unit"] = round((done_unit / total_unit) * 100, 1)
    if total_subj > 0:
        mastery_data["subject"] = round((done_subj / total_subj) * 100, 1)
    if total_grade > 0:
        mastery_data["grade"] = round((done_grade / total_grade) * 100, 1)

    print(f"[TEACHER DEBUG] Final Mastery Data: {mastery_data}")

    result_payload = {
        "messages": [response],
        "current_action": "PROBLEM_GIVEN" if is_knowledge_tracing_mode(learning_mode) else "EXPLAINING",
        "next_dest": "END",
        "mastery": mastery_data,
    }
    if is_knowledge_tracing_mode(learning_mode):
        result_payload["last_problem"] = response.content
    return result_payload

def problem_node(state: AgentState):
    from .database import get_mistakes
    learning_mode = _learning_mode(state)
    mistakes = get_mistakes(state.get("username"), state.get("topic"))
    
    reinforcement_instruction = ""
    if mistakes:
        recent_mistakes = list(set(mistakes[-3:]))
        reinforcement_instruction = f"\n\n**Reinforcement**: The student previously struggled with: {recent_mistakes}. Create a problem that specifically targets these weaknesses to reinforce understanding."

    topic_broad = state['topic']
    current_node = None
    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == state.get("username")).first()
        if player:
            current_node = _select_active_node(db, player, state)
            if current_node:
                touch_current_node(
                    db,
                    player,
                    topic_broad,
                    current_node.id,
                    learning_mode=learning_mode,
                )
                db.commit()
    finally:
        db.close()

    problem_topic = current_node.label if current_node else topic_label_for_mode(topic_broad, learning_mode)
    if is_knowledge_tracing_mode(learning_mode):
        prompt = _build_knowledge_tracing_prompt(state, current_node, state.get("location", "New Hampshire"), "") + reinforcement_instruction
    else:
        prompt = PROBLEM_GENERATOR_PROMPT.format(
            topic=problem_topic,
            grade_level=state['grade_level']
        ) + reinforcement_instruction
    
    print(f"\n[AGENTS] PROBLEM NODE\nPROMPT:\n{prompt}\n")
    
    context_messages = (
        [HumanMessage(content=_knowledge_tracing_request_directive(state['messages'][-1].content if state.get('messages') else "", current_node))]
        if is_knowledge_tracing_mode(learning_mode)
        else state['messages'][-5:]
    )
    full_input = [SystemMessage(content=prompt)] + context_messages
    
    problem_llm, problem_model_name, problem_billing_source, problem_service_tier = _build_llm(
        state,
        _hosted_teacher_model(),
        allow_preferred_model=True,
        priority_enabled=_hosted_teacher_priority_enabled(),
    )
    start_time = time.perf_counter()
    response = problem_llm.invoke(full_input)
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    input_tokens, output_tokens = _extract_usage_metrics(response)
    print(f"RESPONSE:\n{response.content}\n")
    
    log_interaction(
        username=state.get("username", "Unknown"),
        subject=_subject_key_for_topic(topic_broad),
        user_query="[System Triggered Problem Generation]",
        agent_response=response.content,
        source_node="problem_generator",
        session_id=state.get("session_id"),
        topic_name=topic_broad,
        node_id=current_node.id if current_node else _current_node_id_for_state(state),
        model_name=problem_model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        billing_source=problem_billing_source,
        service_tier=problem_service_tier,
        event_type="knowledge_trace_question" if is_knowledge_tracing_mode(learning_mode) else "problem_generated",
    )
    
    return {"messages": [response], "current_action": "PROBLEM_GIVEN", "last_problem": response.content, "next_dest": "END"}

def verifier_node(state: AgentState):
    messages = state['messages']
    last_answer = messages[-1].content
    problem_context = state.get('last_problem', 'Unknown')
    learning_mode = _learning_mode(state)
    
    if not problem_context or problem_context == "Unknown":
        if len(messages) >= 2 and isinstance(messages[-2], BaseMessage):
             problem_context = messages[-2].content
        else:
             problem_context = "Unknown context. Please ask the student to restate the problem."

    prompt = VERIFIER_PROMPT.format(last_problem=problem_context, last_answer=last_answer)
    print(f"\n[AGENTS] VERIFIER NODE\nPROMPT:\n{prompt}\n")
    
    verifier_llm, verifier_model_name, verifier_billing_source, verifier_service_tier = _build_llm(
        state,
        _hosted_verifier_model(),
        allow_preferred_model=True,
        priority_enabled=_hosted_verifier_priority_enabled(),
    )
    start_time = time.perf_counter()
    response = verifier_llm.invoke([SystemMessage(content=prompt)])
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    input_tokens, output_tokens = _extract_usage_metrics(response)
    content = response.content
    print(f"RESPONSE:\n{content}\n")
    is_correct, score_percent, feedback = _parse_verifier_response(content)
    current_node_id = _current_node_id_for_state(state)
    
    log_interaction(
        state.get("username"),
        _subject_key_for_topic(state.get("topic")),
        last_answer,
        feedback,
        "verifier",
        session_id=state.get("session_id"),
        topic_name=state.get("topic"),
        node_id=current_node_id,
        model_name=verifier_model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        billing_source=verifier_billing_source,
        service_tier=verifier_service_tier,
        event_type="answer_evaluation",
        score_percent=score_percent,
        is_correct=is_correct,
    )

    db = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == state.get("username")).first()
        if player and state.get("topic"):
            record_answer_evaluation(
                db,
                player=player,
                topic_name=state.get("topic"),
                node_id=current_node_id,
                is_correct=is_correct,
                score_percent=score_percent,
                problem=problem_context,
                answer=last_answer,
                feedback=feedback,
                learning_mode=learning_mode,
            )
            if is_knowledge_tracing_mode(learning_mode) and current_node_id:
                apply_tracing_result(
                    db,
                    player_id=player.id,
                    topic_name=state.get("topic"),
                    node_id=current_node_id,
                    target_grade=_parse_target_grade(state),
                    is_correct=is_correct,
                    score_percent=score_percent,
                )
            db.commit()
    finally:
        db.close()
    
    # Pass to Adapter
    return {"messages": [AIMessage(content=feedback)], "next_dest": "ADAPTER"}

def adapter_node(state: AgentState):
    """
    Decides on Mastery vs Remediation based on history.
    """
    topic = state.get("topic", "General")
    messages = state['messages']
    learning_mode = _learning_mode(state)

    if is_knowledge_tracing_mode(learning_mode):
        db = SessionLocal()
        try:
            player = db.query(Player).filter(Player.username == state.get("username")).first()
            if not player:
                return {"messages": [], "next_dest": "END"}

            target_grade = _parse_target_grade(state)
            refreshed = refresh_tracing_topic_mastery(db, player.id, topic, target_grade)
            progress = get_topic_progress(db, player.id, topic, learning_mode)

            unit_score = 0.0
            active_node_id = progress.current_node if progress else None
            next_node = select_next_tracing_node(
                db,
                player_id=player.id,
                topic_name=topic,
                target_grade=target_grade,
                current_node_id=active_node_id,
            )
            if next_node:
                touch_current_node(
                    db,
                    player,
                    topic,
                    next_node.id,
                    learning_mode=learning_mode,
                )
                progress = get_topic_progress(db, player.id, topic, learning_mode)
                active_node_id = next_node.id

            current_row = None
            if active_node_id:
                current_row = db.query(StudentNodeProgress).filter(
                    StudentNodeProgress.player_id == player.id,
                    StudentNodeProgress.topic_name == topic,
                    StudentNodeProgress.node_id == active_node_id,
                    StudentNodeProgress.learning_mode == KNOWLEDGE_TRACING_MODE,
                ).first()
            if current_row:
                unit_score = float(int(current_row.mastery_level or 0) * 10)

            done_grade, total_grade = get_all_subjects_stats(player.id, db)
            grade_percent = round((done_grade / total_grade) * 100, 1) if total_grade > 0 else 0.0
            mastery_data = {
                "unit": unit_score,
                "subject": float(refreshed.get("subject_score", 0)),
                "grade": grade_percent,
            }

            latest_feedback = messages[-1].content if messages else ""
            if int(refreshed.get("subject_level", 0)) >= 10:
                follow_up_text = "Full mastery reached for this subject. I can still spot-check you later if needed."
                db.commit()
                combined_content = follow_up_text if latest_feedback == "" else latest_feedback + "\n\n" + follow_up_text
                return {
                    "messages": [AIMessage(content=combined_content)],
                    "current_action": "IDLE",
                    "next_dest": "END",
                    "mastery": mastery_data,
                }

            if next_node is not None:
                db.commit()
                next_question_state = dict(state)
                next_question_state["messages"] = list(messages) + [
                    HumanMessage(content="Ask the next assessment question for the current concept.")
                ]
                next_question_result = teacher_node(next_question_state)
                next_question_messages = next_question_result.get("messages", [])
                next_question_text = next_question_messages[-1].content if next_question_messages else ""
                combined_content = next_question_text if latest_feedback == "" else latest_feedback + "\n\n" + next_question_text
                result_payload = {
                    "messages": [AIMessage(content=combined_content)],
                    "current_action": next_question_result.get("current_action", "PROBLEM_GIVEN"),
                    "next_dest": "END",
                    "mastery": mastery_data,
                }
                if next_question_result.get("last_problem"):
                    result_payload["last_problem"] = next_question_result["last_problem"]
                return result_payload

            db.commit()
            return {"messages": [], "current_action": "IDLE", "next_dest": "END", "mastery": mastery_data}
        finally:
            db.close()
    
    # Extract recent interaction history (last 10 messages) for context
    history_str = ""
    for m in messages[-10:]:
        role = "Student: " if isinstance(m, HumanMessage) else "Agent: "
        history_str += f"{role}{m.content}\n"
        
    prompt = ADAPTER_PROMPT.format(topic=topic, history=history_str)
    
    print(f"\n[AGENTS] ADAPTER NODE\nPROMPT:\n{prompt}\n")
    
    # Force JSON output
    adapter_llm, _adapter_model_name, _adapter_billing_source, _adapter_service_tier = _build_llm(
        state,
        _hosted_fast_model(),
        allow_preferred_model=True,
        priority_enabled=_hosted_fast_priority_enabled(),
    )
    response = adapter_llm.invoke([SystemMessage(content=prompt)])
    content = response.content
    print(f"RESPONSE:\n{content}\n")
    
    decision_data = {}
    try:
        decision_data = json.loads(content)
    except:
        print("Adapter JSON Parse Error")
        decision_data = {"decision": "CONTINUE_PRACTICE"}
        
    decision = decision_data.get("decision", "CONTINUE_PRACTICE")
    remediation_topic = decision_data.get("remediation_topic")
    
    # DB Logic
    user = state.get("username", "Player1")
    new_mastery = -1
    
    if decision == "MASTERED":
        # Mark Complete in DB
        kg = get_graph(topic)
        completed = []
        done_unit, total_unit = 0, 0
        done_subj, total_subj = 0, 0
        done_grade, total_grade = 0, 0
        db = SessionLocal()
        try:
             player = db.query(Player).filter(Player.username == user).first()
             if player:
                prog = get_topic_progress(db, player.id, topic, learning_mode)
                if prog and prog.current_node:
                    current_node_id = prog.current_node
                    mark_node_mastered(db, player, topic, current_node_id, learning_mode=learning_mode)
                    db.flush()
                    db.refresh(prog)
                    completed = list(prog.completed_nodes) if prog.completed_nodes else []
                    print(f"[KG] Node Mastered by Adapter!")
                        
                    # Calculate Multi-Level Mastery
                    subtree_root = None
                    if completed and "->" in completed[-1]:
                         parts = completed[-1].split("->")
                         if len(parts) > 1:
                             subtree_root = "->".join(parts[:-1])
                         else:
                             subtree_root = parts[0]
                         
                    done_unit, total_unit = kg.get_completion_stats(completed, subtree_root)
                    done_subj, total_subj = kg.get_completion_stats(completed)
                    
                    if total_subj > 0:
                        prog.mastery_score = int((done_subj / total_subj) * 100) # Persist Subject Mastery
                        prog.mastery_level = max(0, min(10, int(round(float(prog.mastery_score or 0) / 10.0))))
                        db.commit()
                        
                    done_grade, total_grade = get_all_subjects_stats(player.id, db)
                    
        finally:
            db.close()
            
        mastery_data = {
            "unit": 0.0, "subject": 0.0, "grade": 0.0
        }
        if total_unit > 0: mastery_data["unit"] = round((done_unit / total_unit) * 100, 1)
        if total_subj > 0: mastery_data["subject"] = round((done_subj / total_subj) * 100, 1)
        if total_grade > 0: mastery_data["grade"] = round((done_grade / total_grade) * 100, 1)
            
        # Auto-Advance Logic
        candidate = None
        db = SessionLocal()
        try:
            player = db.query(Player).filter(Player.username == user).first()
            if player:
                candidate = select_next_teach_me_node(
                    db,
                    player_id=player.id,
                    topic_name=topic,
                    target_grade=_parse_target_grade(state),
                )
        finally:
            db.close()
        
        if candidate is not None:
             # Auto-advance
             next_label = candidate.label
             msg = AIMessage(content=f"Excellent work! You've mastered {topic}. Auto-advancing to: {next_label}...")
             return {"messages": [msg], "current_action": "EXPLAINING", "next_dest": "TEACHER", "mastery": new_mastery}

        # Finished
        msg = AIMessage(content=f"Excellent work! You've mastered {topic}. Let's move on!")
        return {"messages": [msg], "current_action": "IDLE", "next_dest": "END", "mastery": new_mastery}

    elif decision == "REMEDIATE" and remediation_topic:
        # Find Prereq
        kg = get_graph(topic)
        db = SessionLocal()
        target_remediation = None
        try:
            player = db.query(Player).filter(Player.username == user).first()
            prog = get_topic_progress(db, player.id, topic, learning_mode)
            if prog and prog.current_node:
                current_node_id = prog.current_node
                prereqs = kg.get_prerequisites(current_node_id)
                if prereqs:
                    target_remediation = prereqs[0] # Pick first one
        finally:
            db.close()
            
        if target_remediation:
             msg = AIMessage(content=f"It seems we should review a prerequisite: {target_remediation}. Let's switch focus.")
             return {"messages": [msg], "current_action": "IDLE", "next_dest": "TEACHER"} 
        
    # Default: Continue
    return {"messages": [], "next_dest": "PROBLEM_GENERATOR"}

def chat_node(state: AgentState):
    print(f"\n[AGENTS] GENERAL CHAT NODE\nMessages: {state['messages']}\n")
    chat_llm, chat_model_name, chat_billing_source, chat_service_tier = _build_llm(
        state,
        _hosted_teacher_model(),
        allow_preferred_model=True,
        priority_enabled=_hosted_teacher_priority_enabled(),
    )
    start_time = time.perf_counter()
    response = chat_llm.invoke(state['messages'])
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    input_tokens, output_tokens = _extract_usage_metrics(response)
    print(f"RESPONSE:\n{response.content}\n")
    
    log_interaction(
        username=state.get("username", "Unknown"),
        subject=_subject_key_for_topic(state.get("topic")),
        user_query=state['messages'][-1].content if state['messages'] else "",
        agent_response=response.content,
        source_node="general_chat",
        session_id=state.get("session_id"),
        topic_name=state.get("topic"),
        node_id=_current_node_id_for_state(state),
        model_name=chat_model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        billing_source=chat_billing_source,
        service_tier=chat_service_tier,
        event_type="general_chat",
    )
    
    return {"messages": [response], "next_dest": "END"}

# Routing function
def route_step(state: AgentState):
    dest = state.get("next_dest", "GENERAL_CHAT")
    if dest == "VERIFIER":
        return "verifier"
    elif dest == "TEACHER":
        return "teacher"
    elif dest == "PROBLEM_GENERATOR":
        return "problem_generator"
    elif dest == "GENERAL_CHAT":
        return "general_chat"
    elif dest == "ADAPTER":
        return "adapter"
    elif dest == "END":
        return "end"
    return "general_chat"

# Graph Construction
def create_graph():
    builder = StateGraph(AgentState)
    
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("teacher", teacher_node)
    builder.add_node("problem_generator", problem_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("adapter", adapter_node)
    builder.add_node("general_chat", chat_node)
    
    builder.set_entry_point("supervisor")
    
    builder.add_conditional_edges(
        "supervisor",
        route_step,
        {
            "verifier": "verifier",
            "teacher": "teacher",
            "problem_generator": "problem_generator",
            "general_chat": "general_chat"
        }
    )
    
    builder.add_edge("verifier", "adapter")
    
    builder.add_conditional_edges(
        "adapter", 
        route_step,
        {
            "teacher": "teacher",
            "problem_generator": "problem_generator",
            "general_chat": "general_chat",
            "end": END
        }
    )
    
    builder.add_edge("teacher", END)
    builder.add_edge("problem_generator", END)
    builder.add_edge("general_chat", END)
    
    return builder
