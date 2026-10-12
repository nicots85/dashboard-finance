"""Optimización de calendarios: mismas fechas, cierres y pausas reales."""
import unittest

import pandas as pd
import pandas_market_calendars as mcal

from src.indices_math import schedule, trading_segments


class CalendarEquivalenceTests(unittest.TestCase):
    def test_cached_calendar_has_identical_dst_holiday_and_early_close_schedule(self):
        for name, start, end in [("NYSE", "2026-03-05", "2026-03-10"), ("NYSE", "2026-11-23", "2026-11-30"),
                                 ("JPX", "2026-10-01", "2026-10-09"), ("CMEGlobex_Gold", "2026-10-01", "2026-10-09")]:
            expected = mcal.get_calendar(name).schedule(start, end)
            pd.testing.assert_frame_equal(schedule(name, start, end), expected)

    def test_vectorized_segments_preserve_lunch_and_market_close(self):
        for name in ("NYSE", "JPX", "CME_Equity"):
            sch = mcal.get_calendar(name).schedule("2026-10-01", "2026-10-09")
            expected = []
            for day, row in sch.iterrows():
                a, b = row.market_open, row.market_close
                b0, b1 = row.get("break_start"), row.get("break_end")
                if pd.notna(b0) and pd.notna(b1) and b1 > b0:
                    expected.extend([(a, b0, str(day.date())), (b1, b, str(day.date()))])
                else:
                    expected.append((a, b, str(day.date())))
            self.assertEqual(trading_segments(name, "2026-10-01", "2026-10-09"), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
