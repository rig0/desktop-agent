"""Desktop Agent Test Suite.

This package contains unit tests, integration tests, and test fixtures
for the Desktop Agent application.

Test Organization:
    tests/
        unit/               - Unit tests for individual modules
            modules/        - Tests for application modules
                core/       - Core functionality tests
                collectors/ - Data collector tests
                monitors/   - Monitor tests
        fixtures/           - Shared test fixtures and factories
        conftest.py         - Pytest configuration and global fixtures

Running Tests:
    # Run all tests
    pytest

    # Run with coverage
    pytest --cov=modules --cov-report=html

    # Run specific test file
    pytest tests/unit/modules/test_messaging.py

    # Run tests matching pattern
    pytest -k test_mqtt

    # Run with verbose output
    pytest -v

    # Run only fast tests (exclude slow tests)
    pytest -m "not slow"
"""
