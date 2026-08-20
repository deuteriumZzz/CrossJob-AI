from src.job_sources.user_agents import USER_AGENTS, random_user_agent


def test_random_user_agent_returns_one_of_the_pool():
    for _ in range(50):
        assert random_user_agent() in USER_AGENTS


def test_user_agent_pool_has_no_duplicates():
    assert len(USER_AGENTS) == len(set(USER_AGENTS))


if __name__ == "__main__":
    test_random_user_agent_returns_one_of_the_pool()
    test_user_agent_pool_has_no_duplicates()
    print("All tests passed.")
