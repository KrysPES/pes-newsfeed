"""One test per source, against a saved fixture, so the suite runs offline."""

import unittest

from support import RUN_DATE, context, fixture

from scanner.fetch import StubFetcher
from scanner.parsers import bls, boe, cftc, clocks, ecb, eia_ngs, eia_steo, eia_wpsr, fed, ons


class ParserTestCase(unittest.TestCase):
    def setUp(self):
        self.ctx = context()

    def assert_shape(self, rows):
        self.assertTrue(rows, "parser returned no rows")
        for row in rows:
            self.assertEqual(row["consensus"], "")
            self.assertEqual(row["actual"], "")
            self.assertTrue(row["source_url"].startswith("https://"))
            self.assertLessEqual(len(row["title"]), 60, row["title"])
            self.assertIn(row["date_source"], ("published", "generated"))
            self.assertTrue(row["detail"])
            self.assertTrue(row["energy_relevance"])


class TestBoe(ParserTestCase):
    def test_parses_confirmed_and_provisional_years(self):
        rows = boe.parse(fixture("boe_mpc.html"), self.ctx)
        self.assert_shape(rows)
        dates = {row["date"] for row in rows}
        self.assertIn("2026-09-17", dates)
        self.assertIn("2027-02-04", dates)
        decisions = [r for r in rows if "MPC decision" in r["title"]]
        self.assertEqual(len(decisions), 16)
        reports = [r for r in rows if "Monetary Policy Report" in r["title"]]
        self.assertEqual(len(reports), 8)
        self.assertEqual(
            rows[0]["title"], "Bank of England MPC decision, February 2026"
        )
        provisional = [r for r in rows if r["date"].startswith("2027")]
        self.assertTrue(all("Provisional" in r["notes"] for r in provisional))
        self.assertTrue(all(r["time"] == "" for r in rows))

    def test_collect_reports_status(self):
        stub = StubFetcher({boe.URL: fixture("boe_mpc.html")})
        rows, status = boe.collect(stub, self.ctx)
        self.assertEqual(status, 200)
        self.assertTrue(rows)

    def test_collect_survives_a_block(self):
        rows, status = boe.collect(StubFetcher({boe.URL: 403}), self.ctx)
        self.assertEqual(status, 403)
        self.assertEqual(rows, [])


class TestFed(ParserTestCase):
    def test_takes_the_last_day_of_each_meeting(self):
        rows = fed.parse(fixture("fed_fomc.html"), self.ctx)
        self.assert_shape(rows)
        dates = {row["date"] for row in rows}
        self.assertIn("2026-09-16", dates)
        self.assertIn("2027-01-27", dates)

    def test_month_spanning_meeting_uses_the_second_month(self):
        rows = fed.parse(fixture("fed_fomc.html"), self.ctx)
        by_title = {row["title"]: row["date"] for row in rows}
        # The fixture labels this meeting 'Apr/May' with the range '30-1'.
        self.assertEqual(
            by_title["FOMC monetary policy decision, May 2024"], "2024-05-01"
        )

    def test_projections_meetings_are_flagged(self):
        rows = fed.parse(fixture("fed_fomc.html"), self.ctx)
        flagged = [r for r in rows if "Summary of Economic Projections" in r["notes"]]
        self.assertTrue(flagged)

    def test_meeting_date_helper(self):
        self.assertEqual(fed._meeting_date(2026, "Apr/May", "28-29").isoformat(), "2026-05-29")
        self.assertEqual(fed._meeting_date(2026, "January", "27-28").isoformat(), "2026-01-28")
        self.assertEqual(fed._meeting_date(2026, "March", "16-17*").isoformat(), "2026-03-17")
        self.assertIsNone(fed._meeting_date(2026, "Nonsense", "1"))


class TestEcb(ParserTestCase):
    def test_only_decision_days_are_kept(self):
        rows = ecb.parse(fixture("ecb_gc.html"), self.ctx)
        self.assert_shape(rows)
        dates = {row["date"] for row in rows}
        self.assertIn("2026-09-10", dates)
        self.assertIn("2026-10-29", dates)
        # Day one of a two day meeting and the non monetary meetings are out.
        self.assertNotIn("2026-09-09", dates)
        self.assertNotIn("2026-09-30", dates)

    def test_titles_carry_the_meeting_month(self):
        rows = ecb.parse(fixture("ecb_gc.html"), self.ctx)
        self.assertIn(
            "ECB monetary policy decision, September 2026",
            {row["title"] for row in rows},
        )


class TestOns(ParserTestCase):
    def test_only_the_named_series_are_kept(self):
        rows = ons.parse(fixture("ons_calendar.html"), self.ctx)
        self.assert_shape(rows)
        labels = {row["title"].split(",")[0] for row in rows}
        self.assertTrue(labels.issubset({
            "ONS consumer price inflation",
            "ONS labour market overview",
            "ONS monthly GDP estimate",
            "ONS first quarterly GDP estimate",
        }), labels)

    def test_release_time_is_converted_to_utc(self):
        rows = ons.parse(fixture("ons_calendar.html"), self.ctx)
        gdp = [r for r in rows if r["title"].startswith("ONS first quarterly")]
        self.assertTrue(gdp)
        # 13 August 2026 is inside British Summer Time, so 07:00 local is 06:00 UTC.
        self.assertEqual(gdp[0]["date"], "2026-08-13")
        self.assertEqual(gdp[0]["time"], "06:00")

    def test_source_url_is_the_harvested_release_link(self):
        rows = ons.parse(fixture("ons_calendar.html"), self.ctx)
        for row in rows:
            self.assertTrue(row["source_url"].startswith("https://www.ons.gov.uk/releases/"))

    def test_reference_period_helper(self):
        self.assertEqual(ons._reference("Consumer price inflation, UK: July 2026"), "July 2026")
        self.assertEqual(ons._reference("No colon here"), "")

    def test_labour_market_release_is_picked_up(self):
        rows = ons.parse(fixture("ons_calendar_page2.html"), self.ctx)
        titles = {row["title"] for row in rows}
        self.assertIn("ONS labour market statistics, August 2026", titles)

    def test_companion_time_series_releases_are_dropped(self):
        page = fixture("ons_calendar_page2.html") + fixture("ons_calendar.html")
        for row in ons.parse(page, self.ctx):
            self.assertNotIn("time series", row["title"].lower())
        self.assertIsNone(ons._series_for("GDP monthly estimate, UK: June 2026 time series"))
        self.assertIsNotNone(ons._series_for("GDP monthly estimate, UK: June 2026"))

    def test_regional_labour_market_releases_are_not_matched(self):
        self.assertIsNone(ons._series_for("Labour market in the regions of the UK: August 2026"))
        self.assertIsNone(ons._series_for("Labour market statistics time series: August 2026"))


class TestBls(ParserTestCase):
    def test_only_cpi_and_payrolls_are_kept(self):
        rows = bls.parse(fixture("bls_ics.ics"), self.ctx)
        self.assert_shape(rows)
        labels = {row["title"].split(",")[0] for row in rows}
        self.assertEqual(
            labels,
            {"US consumer price index release", "US employment situation release"},
        )

    def test_eastern_time_is_converted_to_utc(self):
        rows = bls.parse(fixture("bls_ics.ics"), self.ctx)
        row = [r for r in rows if r["date"] == "2026-08-12"]
        self.assertTrue(row, "expected a release on 12 August 2026")
        # 08:30 US Eastern in August is 12:30 UTC.
        self.assertEqual(row[0]["time"], "12:30")


class TestEiaNgs(ParserTestCase):
    def test_holiday_exceptions_are_published_and_the_rest_generated(self):
        rows = eia_ngs.parse(fixture("eia_ngs.html"), self.ctx)
        self.assert_shape(rows)
        published = [r for r in rows if r["date_source"] == "published"]
        generated = [r for r in rows if r["date_source"] == "generated"]
        self.assertEqual({r["date"] for r in published}, {"2026-11-13", "2026-11-25"})
        self.assertTrue(len(generated) > 50)
        self.assertTrue(all("generated from the standard weekly cadence" in r["notes"] for r in generated))

    def test_generated_rows_do_not_collide_with_an_exception_week(self):
        rows = eia_ngs.parse(fixture("eia_ngs.html"), self.ctx)
        titles = [r["title"] for r in rows]
        self.assertEqual(len(titles), len(set(titles)))

    def test_standard_schedule_is_read_from_the_page(self):
        from scanner.parsers.eia_common import standard_schedule

        weekday, eastern = standard_schedule(fixture("eia_ngs.html"))
        self.assertEqual(weekday, 3)
        self.assertEqual(eastern, "10:30")

    def test_generated_time_is_utc(self):
        rows = eia_ngs.parse(fixture("eia_ngs.html"), self.ctx)
        august = [r for r in rows if r["date"] == "2026-08-06"]
        self.assertTrue(august)
        # 10:30 US Eastern in August is 14:30 UTC.
        self.assertEqual(august[0]["time"], "14:30")


class TestEiaWpsr(ParserTestCase):
    def test_exception_table_with_a_data_week_column(self):
        rows = eia_wpsr.parse(fixture("eia_wpsr.html"), self.ctx)
        self.assert_shape(rows)
        published = [r for r in rows if r["date_source"] == "published"]
        self.assertTrue(published)
        self.assertTrue(any("Covers data for the week ending" in r["notes"] for r in published))
        self.assertIn("2026-09-10", {r["date"] for r in published})

    def test_standard_day_is_wednesday(self):
        from scanner.parsers.eia_common import standard_schedule

        weekday, eastern = standard_schedule(fixture("eia_wpsr.html"))
        self.assertEqual(weekday, 2)
        self.assertEqual(eastern, "10:30")


class TestEiaSteo(ParserTestCase):
    def test_next_release_date(self):
        rows = eia_steo.parse(fixture("eia_steo.html"), self.ctx)
        self.assert_shape(rows)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-08-11")
        self.assertEqual(rows[0]["title"], "EIA Short Term Energy Outlook, August 2026")


class TestCftc(ParserTestCase):
    def test_full_year_of_release_dates(self):
        rows = cftc.parse(fixture("cftc_cot.html"), self.ctx)
        self.assert_shape(rows)
        dates = {row["date"] for row in rows}
        self.assertIn("2026-08-07", dates)
        self.assertIn("2026-12-28", dates)
        self.assertTrue(len(rows) > 20)

    def test_release_time_is_read_from_the_prose(self):
        rows = cftc.parse(fixture("cftc_cot.html"), self.ctx)
        row = [r for r in rows if r["date"] == "2026-08-07"][0]
        # 15:30 US Eastern in August is 19:30 UTC.
        self.assertEqual(row["time"], "19:30")

    def test_holiday_marks_are_carried_into_notes(self):
        rows = cftc.parse(fixture("cftc_cot.html"), self.ctx)
        self.assertTrue(any("federal holiday" in r["notes"] for r in rows))

    def test_two_releases_in_one_week_keep_separate_identities(self):
        rows = cftc.parse(fixture("cftc_cot.html"), self.ctx)
        by_date = {row["date"]: row["title"] for row in rows}
        # 16 and 20 November 2026 sit in the same ISO week.
        self.assertEqual(
            by_date["2026-11-16"], "CFTC Commitments of Traders, 16 November 2026"
        )
        self.assertEqual(
            by_date["2026-11-20"], "CFTC Commitments of Traders, 20 November 2026"
        )
        titles = [row["title"] for row in rows]
        self.assertEqual(len(titles), len(set(titles)))


class TestClocks(ParserTestCase):
    def test_forward_and_back_dates(self):
        rows = clocks.parse(fixture("uk_clocks.html"), self.ctx)
        self.assert_shape(rows)
        pairs = {(row["title"], row["date"]) for row in rows}
        self.assertIn(("UK clocks go back, October 2026", "2026-10-25"), pairs)
        self.assertIn(("UK clocks go forward, March 2027", "2027-03-28"), pairs)


if __name__ == "__main__":
    unittest.main()
