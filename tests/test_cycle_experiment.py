"""Guard against running fault experiments on a live or stale installation."""
import pytest

from evaluation.cycle_server import DATABASE, FIXTURE
from evaluation.cycle_test import current_failure, recovered, validate_marker


@pytest.mark.parametrize('change', [
    {'fixture': 'nexo-live'}, {'database': '/app/data/nexo.db'},
    {'storage': 'volume'}, {'source_sha256': {'evaluation/cycle_protocol.json': 'stale'}},
])
def test_reject_live_persistent_or_stale_fixture(change):
    marker = {'fixture': FIXTURE, 'database': DATABASE, 'storage': 'tmpfs',
              'source_sha256': {'evaluation/cycle_protocol.json': 'expected'}}
    marker.update(change)
    with pytest.raises(AssertionError):
        validate_marker(marker, 'expected')


def test_previous_trial_logs_and_recovery_cannot_satisfy_current_trial():
    assert not current_failure([{'status': 503, 'timestamp_ns': '99'},
                                {'status': 200, 'timestamp_ns': '101'}], 100)
    assert current_failure([{'status': 503, 'timestamp_ns': '100'}], 100)
    case = {'timeline': [{'action': 'Serviço recuperado',
                         'created_at': '2026-10-25T10:00:00+00:00'}]}
    assert recovered(case, 1792922400)
    assert not recovered(case, 1792922401)
