"""
Unit and regression test for the molselect package.
"""

# Import package, test suite, and other packages as needed
import sys

import pytest

import molselect


def test_molselect_imported():
    """Sample test, will always pass so long as import statement worked."""
    assert "molselect" in sys.modules
