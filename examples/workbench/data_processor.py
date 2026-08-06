"""Data-processing helpers for a reporting pipeline. Fill in the bodies."""

import csv


def read_csv_rows(path):
    """Read a CSV file into a list of dicts keyed by header row."""
    ...


def average_by(rows, key):
    # TODO: return the average of rows[*][key]
    ...


def totals_by(rows, group_key, value_key):
    # TODO: group rows by group_key and sum value_key per group
    ...


def top_n(rows, key, n=5):
    ...
