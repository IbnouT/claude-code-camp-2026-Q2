

def test_the_attempt_directory_reaches_the_agent_absolute(tmp_path) -> None:
    """The agent starts elsewhere, so a relative path would point nowhere.

    A run that begins with an empty configuration fails before its first
    model call, which is how two measured runs were lost.
    """
    import os
    from pathlib import Path
    from benchmark.config import AttemptConfig

    config = AttemptConfig(
        directory=Path("relative/attempt"),
        player_profile="poucet",
        player_password_env="MUD_PASSWORD",
        admin_password_env="MUD_ADMIN_PASSWORD",
        profile="direct-full",
        result_mode="full",
        max_turn_cost=0.2,
    )
    value = config.environment()["BOUKENSHA_DIR"]
    assert os.path.isabs(value), value
