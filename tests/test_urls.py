from scripts.utilities import normalize_url, safe_url


def test_tracking_parameters_are_removed_and_query_sorted():
    value = "https://www.example.com/story/?utm_source=rss&b=2&a=1&fbclid=x"
    assert normalize_url(value, ["utm_source", "fbclid"]) == "https://example.com/story?a=1&b=2"


def test_unsafe_schemes_are_rejected():
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("data:text/html,test") is None


def test_localhost_is_rejected():
    assert safe_url("http://localhost/test") is None
