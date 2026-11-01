"""Wellfound: страницы роли ?page=2… читаются, пока приносят новые id."""

from src.job_sources.wellfound.source import WellfoundSource


class _Client:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def search_role_html(self, position, page=1):
        self.calls.append(page)
        return self.pages.get(page, "")

    def get_vacancy_html(self, job_id, slug):
        return ""


def _links(*ids):
    return "".join(f'<a href="/jobs/{i}-python-developer">x</a>' for i in ids)


def test_walks_role_pages_until_nothing_new():
    client = _Client({1: _links(1, 2), 2: _links(2, 3), 3: _links(3)})
    prefs = {"wellfound": {"positions": ["Python Developer"]}}
    jobs = WellfoundSource(client).search(prefs)
    assert sorted(j.external_id for j in jobs) == ["1", "2", "3"]
    assert client.calls == [1, 2, 3]
