from backend.models import ProfileResponse, UpdateProfileRequest


def test_profile_models_include_learning_defaults():
    update_payload = UpdateProfileRequest(
        username="student1",
        grade_level=5,
        location="Texas",
        learning_style="Auditory",
        role="Teacher",
    )
    response_payload = ProfileResponse(
        username="student1",
        avatar_id="schoolgirl",
        grade_level=5,
        location="Texas",
        learning_style="Auditory",
        role="Teacher",
    )

    assert update_payload.grade_level == 5
    assert update_payload.location == "Texas"
    assert update_payload.learning_style == "Auditory"
    assert update_payload.role == "Teacher"
    assert response_payload.grade_level == 5
    assert response_payload.location == "Texas"
    assert response_payload.learning_style == "Auditory"
    assert response_payload.role == "Teacher"
