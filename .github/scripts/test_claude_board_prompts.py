#!/usr/bin/env python3
"""Tests for board-specific Claude prompt builders."""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_board_prompts import (
    build_classify_prompt,
    build_triage_prompt,
    board_token_to_table,
)


class ClaudeBoardPromptTests(unittest.TestCase):
    def test_each_board_prompt_mentions_rules(self):
        titles = ['Software Engineer Intern - Summer 2027']
        summer = build_classify_prompt(titles, 'summer')
        offcycle = build_classify_prompt(titles, 'offcycle')
        newgrad = build_classify_prompt(titles, 'newgrad')
        unknown = build_classify_prompt(titles, 'unknown')

        self.assertIn('Summer 2027', summer)
        self.assertIn('b="s"', summer)
        self.assertIn('Co-op', offcycle)
        self.assertIn('b="o"', offcycle)
        self.assertIn('New Grad', newgrad)
        self.assertIn('b="n"', newgrad)
        self.assertIn('BOARD ROUTING', unknown)
        for p in (summer, offcycle, newgrad, unknown):
            self.assertIn('IN-SCOPE', p)
            self.assertIn('OUT-OF-SCOPE', p)
            self.assertIn('JSON', p)

    def test_prompt_includes_all_titles(self):
        titles = ['Role A', 'Role B', 'Role C']
        prompt = build_classify_prompt(titles, 'summer')
        self.assertIn('1. Role A', prompt)
        self.assertIn('2. Role B', prompt)
        self.assertIn('3. Role C', prompt)
        self.assertIn('length 3', prompt)

    def test_board_token_mapping(self):
        self.assertEqual(board_token_to_table('s'), 'summer')
        self.assertEqual(board_token_to_table('o'), 'offcycle')
        self.assertEqual(board_token_to_table('n'), 'newgrad')
        self.assertIsNone(board_token_to_table('x'))

    def test_triage_prompt_covers_three_boards(self):
        prompt = build_triage_prompt(['1. example'], 1)
        self.assertIn('summer', prompt.lower())
        self.assertIn('off-cycle', prompt.lower())
        self.assertIn('new-grad', prompt.lower())
        self.assertIn('Summer 2027', prompt)


if __name__ == '__main__':
    unittest.main()
