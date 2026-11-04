from src.job_sources.wellfound import client as wf


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


def test_submit_beats_page_apply_button():
    apply_btn, submit = El("Apply"), El("Submit application")
    d = Driver([apply_btn, submit])  # "Apply" раньше в DOM
    assert wf._find_button_by_visible_text(d, wf._SUBMIT_TEXT_MARKERS) is submit


def test_bare_apply_is_not_a_submit_button():
    d = Driver([El("Apply"), El("Apply now")])
    assert wf._find_button_by_visible_text(d, wf._SUBMIT_TEXT_MARKERS) is None


def test_unconfirmed_when_modal_stays(monkeypatch):
    monkeypatch.setattr(wf, "CONFIRM_WAIT_SECONDS", 0.1)
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    d = Driver([El("Submit application")], body="Resume is required")
    assert wf._wait_confirmed(d) is False


def test_confirmed_when_submit_gone():
    d = Driver([El("Apply")], body="")
    assert wf._wait_confirmed(d) is True


def test_wait_for_submit_times_out(monkeypatch):
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    assert wf._wait_for_submit(Driver([El("Apply")]), timeout=0.05) is False
    assert wf._wait_for_submit(Driver([El("Send application")])) is True
