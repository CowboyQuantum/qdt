import pytest

from qdt_lab.simulated import SimulatedLevelSource

# Register real backends here under the `hardware` marker as drivers land (see CLAUDE.md).
LEVEL_SOURCE_BACKENDS = [pytest.param(SimulatedLevelSource, id="simulated")]


@pytest.fixture(params=LEVEL_SOURCE_BACKENDS)
def level_source(request):
    return request.param()
