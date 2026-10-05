"""Test helpers for language adapters: survey a throwaway repo, read its roads."""

import unittest

import fixture
import langkit
import survey


def survey_files(test, files):
    """Commit `files` ({path: text}) to a fresh repository and survey it."""
    return survey.survey(fixture.make_repo(test, files))


def edges(model):
    return set(model.edges)


def needs_grammar(*names):
    """Skip unless every named grammar is installed. Language agents finish with none skipped."""
    missing = [n for n in names if not langkit.grammar_ready(n)]
    return unittest.skipIf(missing, f"grammar not installed: {', '.join(missing)}; "
                                    "run towncode setup")
