import pytest

from qdt_lab.simulated import SimulatedDCSource

# Register real backends here under the `hardware` marker as drivers land (see CLAUDE.md).
DC_BACKENDS = [pytest.param(SimulatedDCSource, id="simulated")]


@pytest.fixture(params=DC_BACKENDS)
def dc_source(request):
    return request.param()
