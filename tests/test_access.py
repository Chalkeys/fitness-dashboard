from dashboard import access


def test_no_owner_configured_means_everyone_is_the_owner():
    # The LAN-only deployment: nothing in front of Streamlit, one user.
    assert access.is_owner({}, owner="")
    assert access.is_owner({"X-Auth-User": "someone"}, owner="")


def test_the_named_user_is_the_owner():
    assert access.is_owner({"X-Auth-User": "fan"}, owner="fan")


def test_anyone_else_is_a_viewer():
    assert not access.is_owner({"X-Auth-User": "guest"}, owner="fan")


def test_no_identity_at_all_is_a_viewer_once_an_owner_exists():
    # A request that reached the app without passing the front is not trusted.
    assert not access.is_owner({}, owner="fan")


def test_cloudflare_access_header_is_recognised():
    assert access.is_owner(
        {"Cf-Access-Authenticated-User-Email": "fan@example.com"}, owner="fan@example.com"
    )


def test_header_names_and_values_compare_case_insensitively():
    assert access.is_owner({"x-auth-user": "Fan"}, owner="fan")
    assert access.is_owner({"CF-ACCESS-AUTHENTICATED-USER-EMAIL": "Fan@Example.com"},
                           owner="fan@example.com")


def test_the_explicit_header_wins_over_cloudflares():
    headers = {"X-Auth-User": "fan", "Cf-Access-Authenticated-User-Email": "other@x"}
    assert access.identity(headers) == "fan"


def test_owner_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(access.OWNER_ENV, "  fan  ")
    assert access.configured_owner() == "fan"
    assert access.is_owner({"X-Auth-User": "fan"})
    assert not access.is_owner({"X-Auth-User": "guest"})
