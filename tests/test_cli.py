from unittest.mock import MagicMock, patch

from construct2_ai_bridge import __main__ as cli


def test_window_opens_after_local_status_is_ready() -> None:
    response = MagicMock()
    response.status = 200
    with (
        patch.object(cli.urllib.request, "urlopen") as urlopen,
        patch.object(cli.webbrowser, "open_new") as open_new,
    ):
        urlopen.return_value.__enter__.return_value = response
        cli._open_window_when_ready("http://127.0.0.1:8765", timeout=0.1)

    urlopen.assert_called_once_with("http://127.0.0.1:8765/api/status", timeout=0.5)
    open_new.assert_called_once_with("http://127.0.0.1:8765")


def test_window_does_not_open_if_service_never_responds() -> None:
    with (
        patch.object(cli.urllib.request, "urlopen", side_effect=OSError("not ready")),
        patch.object(cli.webbrowser, "open_new") as open_new,
        patch.object(cli.time, "sleep"),
        patch.object(cli.time, "monotonic", side_effect=[0.0, 1.0]),
    ):
        cli._open_window_when_ready("http://127.0.0.1:8765", timeout=0.5)

    open_new.assert_not_called()
