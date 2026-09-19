#!/usr/bin/env python3
"""Regression tests for early-career title classification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape_jobs import infer_listing_type, is_auto_addable  # noqa: E402


NEWGRAD = 'New Grad (Full-Time)'
INTERNSHIP = 'Internship'


class InferListingTypeTests(unittest.TestCase):
    def assert_type(self, title: str, expected: str):
        listing_type, _season = infer_listing_type(title)
        self.assertEqual(
            listing_type,
            expected,
            msg=f'{title!r} -> {listing_type!r}, expected {expected!r}',
        )

    def test_doordash_entry_level_graduation_window_is_newgrad(self):
        self.assert_type(
            'Software Engineer I, Entry-Level (Graduation Date: Fall 2026-Summer 2027) - US',
            NEWGRAD,
        )
        self.assertTrue(is_auto_addable(
            'Software Engineer I, Entry-Level (Graduation Date: Fall 2026-Summer 2027) - US'
        ))

    def test_product_design_entry_level_is_newgrad(self):
        self.assert_type('Product Design, Entry-Level (2027 start)', NEWGRAD)

    def test_barclays_graduate_program_is_newgrad(self):
        self.assert_type('2027 Technology Developer Graduate Program Whippany', NEWGRAD)
        self.assert_type(
            '2027 Technology Developer Expert Graduate Program Wilmington',
            NEWGRAD,
        )
        self.assertTrue(is_auto_addable('2027 Technology Developer Graduate Program Whippany'))

    def test_bny_analyst_program_is_newgrad(self):
        self.assert_type('2027 BNY Analyst Program - Engineering (Developer)', NEWGRAD)
        self.assert_type('2027 BNY Analyst Program - Engineering (Data Science)', NEWGRAD)
        self.assert_type('2027 BNY Analyst Program - Trading', NEWGRAD)
        self.assert_type('2027 BNY Analyst Program - Product Management', NEWGRAD)

    def test_amex_campus_full_time_is_newgrad(self):
        self.assert_type(
            'Campus Undergraduate Full-Time Engineer - 2027 Software Engineer I, '
            'Enterprise Technology Services',
            NEWGRAD,
        )

    def test_true_interns_stay_internship(self):
        cases = [
            'Software Engineer Intern (Fall 2026)',
            'Fall 2026 Software Engineer Intern',
            '2027 BNY Summer Internship Program - Engineering (Developer)',
            'Quantitative Finance Associate Summer Internship Program 2027 New York',
            'Campus Undergraduate Summer Internship Program - 2027 Software Engineer',
            'Graduate Software Engineer Intern 2027',
            'Technology Graduate Intern',
            'Software Engineering Internships',
            'Software PhD Internships',
        ]
        for title in cases:
            with self.subTest(title=title):
                self.assert_type(title, INTERNSHIP)
                self.assertTrue(is_auto_addable(title))

        # Bare engineering titles are campus-shaped but out of CS/IS scope.
        self.assert_type('Engineering Interns', INTERNSHIP)
        self.assertFalse(is_auto_addable('Engineering Interns'))


if __name__ == '__main__':
    unittest.main()
