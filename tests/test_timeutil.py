import unittest
from unittest.mock import patch

from mew import timeutil


class TimeUtilTests(unittest.TestCase):
    def tearDown(self):
        timeutil.reset_dilation()

    def test_now_iso_uses_time_dilation(self):
        timeutil.enable_dilation(10.0, start_real=1000.0, start_logical=0.0)

        with patch("mew.timeutil.time.time", return_value=1006.0):
            self.assertEqual(timeutil.now_iso(), "1970-01-01T00:01:00Z")

    def test_now_date_iso_uses_time_dilation(self):
        timeutil.enable_dilation(8640.0, start_real=100.0, start_logical=0.0)

        with patch("mew.timeutil.time.time", return_value=110.0):
            self.assertEqual(timeutil.now_date_iso(), "1970-01-02")

    def test_reset_dilation_restores_multiplier(self):
        timeutil.enable_dilation(24.0)

        timeutil.reset_dilation()

        self.assertEqual(timeutil.dilation_multiplier(), 1.0)

    def test_enable_dilation_rejects_non_positive_multiplier(self):
        with self.assertRaises(ValueError):
            timeutil.enable_dilation(0)
