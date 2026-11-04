from src.job_sources.himalayas import apply as hm


class El:
    def __init__(self, text):
        self.text = text

    def is_displayed(self):
        return True


class Driver:
    def __init__(self, buttons, body=""):
        self.buttons, self.body = buttons, body

    def find_elements(self, *_):
        return self.buttons

    def find_element(self, *_):
        return El(self.body)


def test_submit_markers_do_not_match_apply_now():
    d = Driver([El("Apply now")])
    assert hm._find_button_by_visible_text(d, hm._SUBMIT_TEXT_MARKERS) is None


def test_submit_priority_over_dom_order():
    submit = El("Submit application")
    d = Driver([El("Submit"), submit])
    assert hm._find_button_by_visible_text(d, hm._SUBMIT_TEXT_MARKERS) is submit


def test_confirmed_only_when_modal_closed(monkeypatch):
    monkeypatch.setattr(hm.time, "sleep", lambda s: None)
    monkeypatch.setattr(hm, "CONFIRM_WAIT_SECONDS", 0.05)
    assert hm._wait_confirmed(Driver([El("I'm ready to apply")])) is False
    assert hm._wait_confirmed(Driver([El("Save")])) is True
    assert hm._wait_confirmed(Driver([], body="Something went wrong")) is False
