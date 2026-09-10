# Financial AI Agent - Test Suite

This directory contains comprehensive tests for the Financial AI Agent system.

## Test Structure

```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── models/                  # Specialized model tests
│   ├── test_pii_detector.py
│   ├── test_sentiment_analyzer.py
│   ├── test_product_classifier.py
│   └── test_policy_classifier.py
├── integration/             # Integration tests
│   └── test_models_integration.py
└── api/                     # API endpoint tests
    ├── test_chat_endpoint.py
    └── test_admin_endpoint.py
```

## Test Categories

### Unit Tests (`@pytest.mark.unit`)
- Fast, isolated tests with no external dependencies
- Mock all external services and APIs
- Test individual functions and classes
- Run in < 30 seconds total

### Integration Tests (`@pytest.mark.integration`)
- Test component interactions
- May require running services (Redis, Qdrant, Postgres)
- Test end-to-end workflows
- Run with real or containerized dependencies

### Model Tests (`@pytest.mark.models`)
- Specialized tests for ML/AI models
- Test PII detection, sentiment analysis, classification
- Include both unit and integration scenarios
- Mock LLM calls for consistency

### API Tests (`@pytest.mark.api`)
- Test FastAPI endpoints
- Test request/response handling
- Test authentication and authorization
- Test error handling and edge cases

### Slow Tests (`@pytest.mark.slow`)
- Tests that take > 5 seconds
- Large data processing tests
- Real API integration tests
- Skipped in fast test runs

## Running Tests

### Basic Commands

```bash
# All tests
pytest

# Specific categories
pytest -m unit
pytest -m integration
pytest -m models
pytest -m api

# Fast tests only (skip slow)
pytest -m "not slow"

# Specific test file
pytest tests/models/test_pii_detector.py

# Verbose output
pytest -v

# With coverage
pytest --cov=app --cov-report=html
```

### Using Make Commands

```bash
# All tests
make test

# Specific categories
make test-unit
make test-integration
make test-models
make test-api

# With coverage report
make test-coverage

# Fast tests only
make test-fast
```

### Using the Test Runner Script

```bash
# All tests
python scripts/run_tests.py

# Unit tests only
python scripts/run_tests.py --unit

# Integration tests with coverage
python scripts/run_tests.py --integration --coverage

# Fast tests with parallel execution
python scripts/run_tests.py --fast --parallel 4

# Specific test file
python scripts/run_tests.py tests/models/test_pii_detector.py
```

## Test Configuration

### Environment Setup

Tests use a separate test environment with:
- Test database (SQLite or separate Postgres DB)
- Test Redis database (db=1)  
- Mock external APIs by default
- Test-specific configuration overrides

### Required Environment Variables

```bash
# Test environment
APP_ENV=test

# Test database
DATABASE_URL=postgresql+asyncpg://finai:finai123@localhost:5432/finai_test

# Test cache
REDIS_URL=redis://localhost:6379/1

# Mock API keys (for testing)
OPENAI_API_KEY=test-key
SECRET_KEY=test-secret-key-for-testing-only
```

### Fixtures

Key fixtures available in all tests:

- `test_settings`: Override app settings for testing
- `test_client`: HTTP client for API testing
- `mock_openai`: Mocked OpenAI client
- `mock_qdrant`: Mocked Qdrant client
- `sample_*_data`: Sample data for various scenarios

## Writing Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`

### Example Test Structure

```python
import pytest
from unittest.mock import patch, AsyncMock

@pytest.mark.models
@pytest.mark.unit
class TestPIIDetector:
    """Test suite for PII Detection model."""
    
    @pytest.fixture
    def pii_detector(self):
        """Create PII detector instance."""
        return PIIDetector()
    
    @pytest.mark.asyncio
    async def test_detect_pii_with_ssn(self, pii_detector):
        """Test SSN detection and masking."""
        text = "My SSN is 123-45-6789"
        
        with patch('presidio_analyzer.AnalyzerEngine.analyze') as mock_analyze:
            mock_analyze.return_value = [
                MagicMock(entity_type="US_SSN", score=0.95)
            ]
            
            result = await pii_detector.detect_pii(text)
            
            assert result.has_pii is True
            assert result.risk_level == "high"
```

### Test Markers

Always use appropriate markers:

```python
@pytest.mark.unit          # Fast, isolated test
@pytest.mark.integration   # Component interaction test  
@pytest.mark.models        # Model-specific test
@pytest.mark.api           # API endpoint test
@pytest.mark.slow          # Test takes > 5 seconds
@pytest.mark.asyncio       # Async test function
```

### Mocking Guidelines

1. **Mock External Dependencies**: Always mock external APIs, databases, and services in unit tests
2. **Mock at the Right Level**: Mock at the integration boundary, not internal functions
3. **Use Realistic Data**: Mock responses should match real API responses
4. **Test Error Cases**: Mock failures and timeouts to test error handling

### Coverage Requirements

- Minimum 80% code coverage
- All critical paths must be tested
- Error handling must be tested
- Edge cases and validation must be covered

## Continuous Integration

### GitHub Actions

Tests run automatically on:
- Pull requests to `main` or `develop`
- Pushes to `main` or `develop`
- Multiple Python versions (3.11, 3.12)

### Test Services

CI environment includes:
- PostgreSQL 16
- Redis 7.4
- Qdrant vector database
- All required environment variables

### Coverage Reporting

- Coverage reports uploaded to Codecov
- HTML coverage reports generated as artifacts
- Minimum coverage threshold enforced

## Manual Testing

### Interactive Model Testing

```bash
# Run interactive model tests
python scripts/test_models_manual.py

# Test specific models manually
python -c "
import asyncio
from app.models.specialized import get_pii_detector

async def test():
    detector = await get_pii_detector()
    result = await detector.detect_pii('My SSN is 123-45-6789')
    print(result)

asyncio.run(test())
"
```

### API Testing with curl

```bash
# Test chat endpoint
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Help with my account", "session_id": "test"}'

# Test health endpoint
curl "http://localhost:8000/health"

# Test admin status (requires auth)
curl "http://localhost:8000/api/v1/admin/status" \
  -H "X-API-Key: your-secret-key"
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `PYTHONPATH` includes project root
2. **Service Connection Errors**: Check that required services are running
3. **Permission Errors**: Check file permissions on test directories
4. **Mock Failures**: Verify mock patches match actual function signatures

### Debug Mode

Run tests with debug output:

```bash
pytest -v -s --tb=long
```

### Test Isolation

If tests interfere with each other:

```bash
# Run tests in separate processes
pytest -n auto

# Run specific test in isolation
pytest tests/models/test_pii_detector.py::TestPIIDetector::test_detect_pii_with_ssn -v
```

### Performance Issues

For slow test runs:

```bash
# Profile test execution
pytest --durations=10

# Run only fast tests
pytest -m "not slow"

# Use parallel execution
pytest -n 4
```

## Contributing

### Adding New Tests

1. Place tests in appropriate directory (`models/`, `api/`, `integration/`)
2. Use proper test markers and naming conventions
3. Include both positive and negative test cases
4. Add fixtures to `conftest.py` if reusable
5. Update this README if adding new test categories

### Test Review Checklist

- [ ] Tests cover critical functionality
- [ ] Error cases are tested
- [ ] Appropriate mocking is used
- [ ] Tests are fast and isolated
- [ ] Proper markers are applied
- [ ] Documentation is updated
- [ ] Coverage requirements are met