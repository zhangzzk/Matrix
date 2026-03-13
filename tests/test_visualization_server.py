import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dreamdive.visualization_server import start_visualization_server


class _FakeServer:
    def __init__(self, host: str, port: int) -> None:
        chosen_port = 43123 if port == 0 else port
        self.server_address = (host, chosen_port)

    def server_close(self) -> None:
        return None


class VisualizationServerTests(unittest.TestCase):
    def test_start_visualization_server_uses_requested_port_when_available(self) -> None:
        created = []

        def fake_server(address, handler):
            host, port = address
            server = _FakeServer(host, port)
            created.append(server)
            return server

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "dreamdive.visualization_server.ThreadingHTTPServer",
            side_effect=fake_server,
        ):
            server, actual_port = start_visualization_server(
                root_dir=Path(tmpdir),
                host="127.0.0.1",
                port=0,
            )

        self.assertEqual(actual_port, 43123)
        self.assertIs(server, created[0])

    def test_start_visualization_server_falls_back_when_port_is_occupied(self) -> None:
        attempts = []

        def fake_server(address, handler):
            host, port = address
            attempts.append(port)
            if port == 9000:
                raise OSError(errno.EADDRINUSE, "Address already in use")
            return _FakeServer(host, port)

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "dreamdive.visualization_server.ThreadingHTTPServer",
            side_effect=fake_server,
        ):
            server, actual_port = start_visualization_server(
                root_dir=Path(tmpdir),
                host="127.0.0.1",
                port=9000,
                port_search_limit=5,
            )

        self.assertEqual(attempts[:2], [9000, 9001])
        self.assertEqual(actual_port, 9001)
        self.assertEqual(server.server_address[1], 9001)


if __name__ == "__main__":
    unittest.main()
