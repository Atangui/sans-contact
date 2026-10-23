import os
import socket

from sanscontact.privacy.endpoints import EndpointWatch, endpoints


def test_sees_our_own_listening_socket_and_nothing_else_by_default():
    before = endpoints()
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        found = [e for e in endpoints() if e.listening and e.local.endswith(f":{port}")]
        assert len(found) == 1 and found[0].pid == os.getpid()
        watch = EndpointWatch()
        assert watch.poll() >= 1
    finally:
        server.close()
    assert all(e.pid == os.getpid() for e in before)


def test_other_processes_are_not_reported():
    assert all(e.pid == os.getpid() for e in endpoints())
    assert endpoints(pids=[]) == []
