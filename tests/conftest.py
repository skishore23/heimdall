"""
Pytest configuration and fixtures
"""

import asyncio
import importlib
import tempfile
from pathlib import Path

import pytest

from heimdall import clear_registry


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def ensure_guards_registered():
    """Ensure all guard packs are registered before each test"""
    clear_registry()

    # Import and reload guard packs to ensure decorators are executed
    import guards.business.guards
    import guards.pii.guards
    import guards.politics.guards
    import guards.safety.guards
    import guards.schema.guards
    import guards.tools.guards
    import guards.toxicity.guards

    # Reload modules to re-execute @register_factory decorators
    importlib.reload(guards.pii.guards)
    importlib.reload(guards.politics.guards)
    importlib.reload(guards.toxicity.guards)
    importlib.reload(guards.schema.guards)
    importlib.reload(guards.tools.guards)
    importlib.reload(guards.safety.guards)
    importlib.reload(guards.business.guards)

    yield

    # Don't clear after - let next test's clear_registry() handle it


@pytest.fixture
def temp_policy_dir():
    """Create temporary directory for policy files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_policy_yaml():
    """Sample policy YAML content"""
    return """
policy: test_policy
guards:
  - id: pii.redact
    target: messages[*].content
    with:
      types: ["EMAIL"]
      mode: "mask"

  - id: politics.block
    target: output.text
    with:
      patterns_strong: ["\\bvote for\\b"]
      threshold: 0.75

compose:
  root: allOf(pii.redact, politics.block)
"""


@pytest.fixture
def sample_messages():
    """Sample chat messages"""
    return [
        {"role": "user", "content": "Send an email to john@example.com about the meeting"},
        {"role": "assistant", "content": "I'll help you draft an email about the meeting."}
    ]


@pytest.fixture
def sample_output():
    """Sample output content"""
    return "I'll help you draft an email about the meeting."


@pytest.fixture
def sample_political_output():
    """Sample political content that should be blocked"""
    return "You should vote for the candidate in the upcoming election."
