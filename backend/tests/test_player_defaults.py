from backend.database import Player, apply_player_defaults


def test_apply_player_defaults_repairs_manual_player_row():
    player = Player(
        username="manual-admin",
        xp=None,
        level=None,
        location=None,
        grade_level=None,
        learning_style=None,
        sex=None,
        role="Admin",
        display_name=None,
        account_status=None,
        avatar_id=None,
        curriculum_region=None,
        subscription_status_cached=None,
    )

    changed = apply_player_defaults(player)

    assert changed is True
    assert player.xp == 0
    assert player.level == 1
    assert player.location == "New Hampshire"
    assert player.grade_level == 10
    assert player.learning_style == "Visual"
    assert player.sex == "Not Specified"
    assert player.role == "Admin"
    assert player.display_name == "manual-admin"
    assert player.account_status == "active"
    assert player.avatar_id is not None
    assert player.curriculum_region == "New Hampshire"
    assert player.subscription_status_cached == "inactive"
