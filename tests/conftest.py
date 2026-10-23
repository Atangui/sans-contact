import pytest

from sanscontact.privacy import network_guard


@pytest.fixture
def blocked_network():
    """Run a test with the network kill switch installed, then restore it."""
    network_guard.reset_counter()
    network_guard.install()
    try:
        yield
    finally:
        network_guard.uninstall()
        network_guard.reset_counter()
