"""Unit tests for services/ssh_pattern.py — ssh_match() glob semantics."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from services.ssh_pattern import ssh_match


# ─── Exact matches ────────────────────────────────────────────────────────────

def test_exact_ip_matches():
    assert ssh_match("10.0.0.1", ["10.0.0.1"])


def test_exact_ip_no_match():
    assert not ssh_match("10.0.0.2", ["10.0.0.1"])


def test_exact_hostname_matches():
    assert ssh_match("jumpbox.corp", ["jumpbox.corp"])


# ─── Wildcard * ───────────────────────────────────────────────────────────────

def test_wildcard_matches_any_string():
    assert ssh_match("anything.corp", ["*.corp"])


def test_wildcard_star_alone_matches_all():
    assert ssh_match("10.0.0.1", ["*"])
    assert ssh_match("some-host", ["*"])


def test_wildcard_prefix():
    assert ssh_match("dev-box", ["dev-*"])


def test_wildcard_no_match():
    assert not ssh_match("prod.example.com", ["dev.*"])


# ─── Single-char wildcard ? ───────────────────────────────────────────────────

def test_question_mark_matches_one_char():
    assert ssh_match("host1", ["host?"])


def test_question_mark_does_not_match_multiple():
    assert not ssh_match("host12", ["host?"])


# ─── Negation ─────────────────────────────────────────────────────────────────

def test_negation_excludes_match():
    assert not ssh_match("jb.corp", ["*.corp", "!jb.corp"])


def test_negation_allows_other_hosts():
    assert ssh_match("other.corp", ["*.corp", "!jb.corp"])


def test_negation_with_wildcard():
    assert not ssh_match("internal.corp", ["*", "!internal.corp"])


def test_negation_only_list_never_matches():
    """No positive patterns → nothing should match."""
    assert not ssh_match("10.0.0.1", ["!10.0.0.1"])
    assert not ssh_match("anything", ["!other"])


# ─── Case-insensitivity ───────────────────────────────────────────────────────

def test_case_insensitive_candidate():
    assert ssh_match("JUMPBOX.CORP", ["jumpbox.corp"])


def test_case_insensitive_pattern():
    assert ssh_match("jumpbox.corp", ["JUMPBOX.CORP"])


def test_case_insensitive_wildcard():
    assert ssh_match("JB.CORP", ["jb.*"])


def test_case_insensitive_negation():
    assert not ssh_match("JB.CORP", ["*.corp", "!JB.CORP"])


# ─── Multiple positive patterns (any match is enough) ─────────────────────────

def test_multiple_positives_first_matches():
    assert ssh_match("db01", ["db*", "web*"])


def test_multiple_positives_second_matches():
    assert ssh_match("web01", ["db*", "web*"])


def test_multiple_positives_none_match():
    assert not ssh_match("app01", ["db*", "web*"])


# ─── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_aliases_never_matches():
    assert not ssh_match("anything", [])


def test_empty_candidate_with_star():
    assert ssh_match("", ["*"])


def test_empty_candidate_exact_no_match():
    assert not ssh_match("", ["host"])
