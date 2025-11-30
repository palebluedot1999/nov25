# Tests

Unit tests for the hedge fund portfolio tracker application.

## Running Tests

### Run all tests
```bash
# From project root
pytest tests/

# With verbose output
pytest tests/ -v

# With coverage report
pytest tests/ --cov=utils --cov=scrapers
```

### Run specific test file
```bash
pytest tests/test_security_operations.py -v
```

### Run specific test class
```bash
pytest tests/test_security_operations.py::TestSecurityOperations -v
```

### Run specific test
```bash
pytest tests/test_security_operations.py::TestSecurityOperations::test_add_by_cusip_only -v
```

## Test Files

- `test_security_operations.py` - Tests for CUSIP/ticker resolution and cache operations

## Requirements

Make sure pytest is installed:
```bash
pip install pytest pytest-cov
```

## Notes

- Some tests require OpenFIGI API access (configured in `config/settings.py`)
- Tests that modify the CUSIP cache will affect your local data
- Consider creating a separate test environment or test cache file for isolated testing
