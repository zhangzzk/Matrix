from __future__ import annotations

import errno
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote


def build_visualization_url(
    *,
    host: str,
    port: int,
    session_relative_path: str,
) -> str:
    encoded_session = quote(session_relative_path)
    return f"http://{host}:{port}/visualization/?session={encoded_session}"


def start_visualization_server(
    *,
    root_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    port_search_limit: int = 20,
) -> tuple[ThreadingHTTPServer, int]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(root_dir))
    last_error: OSError | None = None
    for candidate_port in _candidate_ports(port, search_limit=port_search_limit):
        try:
            server = ThreadingHTTPServer((host, candidate_port), handler)
            actual_port = int(server.server_address[1])
            return server, actual_port
        except OSError as exc:
            last_error = exc
            if exc.errno != errno.EADDRINUSE:
                raise
            continue
    if last_error is not None:
        raise last_error
    raise OSError("Unable to bind visualization server")


def _candidate_ports(port: int, *, search_limit: int) -> list[int]:
    requested = max(0, int(port))
    if requested == 0:
        return [0]

    candidates = [requested]
    upper_bound = 65535
    for offset in range(1, max(0, search_limit) + 1):
        candidate = requested + offset
        if candidate > upper_bound:
            break
        candidates.append(candidate)
    if 0 not in candidates:
        candidates.append(0)
    return candidates


def run_visualization_server(
    *,
    root_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    server, _actual_port = start_visualization_server(
        root_dir=root_dir,
        host=host,
        port=port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
