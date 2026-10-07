from pathlib import Path

from src.utils import shared_browser as sb


class _Switch:
    def __init__(self, d):
        self.d = d

    def window(self, h):
        self.d.current_window_handle = h

    def new_window(self, _kind):
        h = f"w{len(self.d.window_handles)}"
        self.d.window_handles.append(h)
        self.d.current_window_handle = h


class FakeDriver:
    def __init__(self):
        self.window_handles = ["w0"]
        self.current_window_handle = "w0"
        self.switch_to = _Switch(self)
        self.launched_minimized = False

    def minimize_window(self):
        self.launched_minimized = True

    def close(self):
        self.window_handles.remove(self.current_window_handle)

    def get(self, url):
        self.url = url

    def quit(self):
        pass


def test_one_browser_many_tabs(tmp_path: Path):
    sb._shutdown()
    launches = []

    def launch(p):
        launches.append(p)
        return FakeDriver()

    a = sb.open_tab(tmp_path / ".chrome_profile_a", launch)
    b = sb.open_tab(tmp_path / ".chrome_profile_b", launch)
    assert len(launches) == 1 and launches[0].parent == tmp_path
    assert launches[0].name == sb.SHARED_PROFILE_NAME
    assert len(a._real.window_handles) == 2 and a._real.launched_minimized
    a.quit()
    assert len(b._real.window_handles) == 1
    b.quit()  # последняя вкладка остаётся — окно не умирает
    assert len(b._real.window_handles) == 1
    sb.open_tab(tmp_path / ".chrome_profile_c", launch)
    assert len(launches) == 1
    sb._shutdown()
