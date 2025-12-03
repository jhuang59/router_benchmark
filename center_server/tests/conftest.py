"""
Pytest configuration for center server tests
"""
import os
import tempfile
import pytest

# Create a temporary directory for test data before any imports
# This needs to happen at module level, before app.py is imported
_test_data_dir = tempfile.mkdtemp(prefix='center_server_tests_')
os.environ['DATA_DIR'] = _test_data_dir


def pytest_sessionfinish(session, exitstatus):
    """Clean up temporary directory after all tests"""
    import shutil
    if os.path.exists(_test_data_dir):
        shutil.rmtree(_test_data_dir)
