"""Synthetic public error-code fidelity: no private symbols, keys or data."""
import unittest

import private_lifecycle as lifecycle
from private_sheet_writer import HandoffBlocked


class LifecycleFailureDiagnosticsTests(unittest.TestCase):
    def test_missing_completed_session_uses_categorical_reason(self):
        err = ValueError('FOLLOWUP_ASOF_BAR_MISSING_NO_ADVANCE')
        self.assertEqual(lifecycle.lifecycle_public_failure_code(err),
                         'LIFECYCLE_FOLLOWUP_ASOF_BAR_MISSING')

    def test_intermediate_session_gap_uses_categorical_reason(self):
        err = ValueError('FOLLOWUP_MISSING_INTERMEDIATE_SESSION')
        self.assertEqual(lifecycle.lifecycle_public_failure_code(err),
                         'LIFECYCLE_FOLLOWUP_INTERMEDIATE_SESSION_MISSING')

    def test_duplicated_provider_date_uses_categorical_reason(self):
        err = ValueError('DUPLICATE_FOLLOWUP_BAR')
        self.assertEqual(lifecycle.lifecycle_public_failure_code(err),
                         'LIFECYCLE_FOLLOWUP_DUPLICATE_BAR')

    def test_invalid_ohlcv_refused_with_safe_code(self):
        err = ValueError('INVALID_FOLLOWUP_OHLCV')
        self.assertEqual(lifecycle.lifecycle_public_failure_code(err),
                         'LIFECYCLE_FOLLOWUP_INVALID_OHLCV')

    def test_invalid_bar_range_refused_with_safe_code(self):
        err = ValueError('INVALID_FOLLOWUP_BAR_RANGE')
        self.assertEqual(lifecycle.lifecycle_public_failure_code(err),
                         'LIFECYCLE_FOLLOWUP_INVALID_RANGE')

    def test_any_untrusted_exception_text_remains_unclassified(self):
        for message in ('FOLLOWUP_ASOF_BAR_MISSING_NO_ADVANCE token=secret',
                        'some/private/filename', 'ROKU'):
            with self.subTest(message=message):
                self.assertEqual(lifecycle.lifecycle_public_failure_code(
                    ValueError(message)), 'UNCLASSIFIED')

    def test_wrong_exception_type_cannot_spoof_known_error(self):
        self.assertEqual(lifecycle.lifecycle_public_failure_code(
            RuntimeError('FOLLOWUP_ASOF_BAR_MISSING_NO_ADVANCE')),
            'UNCLASSIFIED')

    def test_existing_allowlisted_handoff_reason_unchanged(self):
        self.assertEqual(lifecycle.lifecycle_public_failure_code(
            HandoffBlocked('LIFECYCLE_MISSING_SYMBOL_BARS')),
            'LIFECYCLE_MISSING_SYMBOL_BARS')


if __name__ == '__main__':
    unittest.main()
