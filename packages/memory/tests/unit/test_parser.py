"""Tests for CodeParser (tree-sitter AST chunking)."""

from __future__ import annotations

import pytest

from packages.memory.src.indexer.grammars import GrammarLoader
from packages.memory.src.indexer.parser import CodeParser


@pytest.fixture
def parser() -> CodeParser:
    return CodeParser(grammar_loader=GrammarLoader())


SAMPLE_PYTHON = '''"""Auth module."""

import hashlib
import secrets
import time
from typing import Optional


# Constants for token generation
TOKEN_PREFIX = "token-"
TOKEN_LENGTH = 32
MAX_ATTEMPTS = 3
SESSION_TIMEOUT = 3600


def login(username: str, password: str) -> str:
    """Authenticate a user and return a token."""
    if not username:
        raise ValueError("Username required")
    if not password:
        raise ValueError("Password required")
    hashed = hashlib.sha256(password.encode()).hexdigest()
    token = TOKEN_PREFIX + secrets.token_hex(TOKEN_LENGTH)
    return token


def logout(token: str) -> bool:
    """Invalidate a session token."""
    if not token.startswith(TOKEN_PREFIX):
        return False
    return True


def refresh_token(old_token: str) -> str:
    """Generate a new token from an existing one."""
    if not old_token.startswith(TOKEN_PREFIX):
        raise ValueError("Invalid token")
    return TOKEN_PREFIX + secrets.token_hex(TOKEN_LENGTH)


class AuthService:
    """Manages authentication."""

    def __init__(self, db):
        self.db = db
        self._sessions = {}

    def verify(self, token: str) -> bool:
        """Verify a JWT token."""
        return token.startswith(TOKEN_PREFIX)

    def get_user(self, token: str) -> Optional[str]:
        """Get user associated with token."""
        if not self.verify(token):
            return None
        return self._sessions.get(token)
'''

SAMPLE_SHORT = '''"""Short module."""

x = 42
'''


class TestCodeParser:
    """Tests for tree-sitter code parsing."""

    def test_parse_python_functions(self, parser) -> None:
        """Should extract function and class chunks from Python."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        names = [c.symbol_name for c in chunks]
        assert "login" in names
        assert "AuthService" in names

    def test_chunk_has_correct_metadata(self, parser) -> None:
        """Chunks should have file_path, language, module_name."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        for chunk in chunks:
            assert chunk.file_path == "src/auth.py"
            assert chunk.language == "python"
            assert chunk.module_name == "auth"

    def test_short_file_single_chunk(self, parser) -> None:
        """Files < 50 lines should produce a single whole-file chunk."""
        chunks = parser.parse(
            content=SAMPLE_SHORT,
            file_path="src/constants.py",
            language="python",
            module_name="constants",
        )
        assert len(chunks) == 1
        assert chunks[0].symbol_type == "module"

    def test_chunk_id_format(self, parser) -> None:
        """chunk_id should be file_path::symbol_name."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        for chunk in chunks:
            assert chunk.chunk_id.startswith("src/auth.py::")

    def test_docstrings_extracted(self, parser) -> None:
        """Functions with docstrings should have docstring field set."""
        chunks = parser.parse(
            content=SAMPLE_PYTHON,
            file_path="src/auth.py",
            language="python",
            module_name="auth",
        )
        login_chunk = next(c for c in chunks if c.symbol_name == "login")
        assert login_chunk.docstring is not None
        assert "Authenticate" in login_chunk.docstring

    def test_unsupported_language_returns_single_chunk(self, parser) -> None:
        """Unsupported language should return whole-file chunk."""
        chunks = parser.parse(
            content="some content",
            file_path="data.csv",
            language="csv",
            module_name="data",
        )
        assert len(chunks) == 1
        assert chunks[0].symbol_type == "module"

    def test_markdown_returns_section_chunks(self, parser) -> None:
        """Markdown files should be split by ## headings."""
        # Build a markdown doc > 50 lines so it doesn't hit the short-file path
        section_a_lines = "\n".join(f"Line {i} of section A content." for i in range(1, 26))
        section_b_lines = "\n".join(f"Line {i} of section B content." for i in range(1, 26))
        md = f"# Title\n\nIntro paragraph.\n\n## Section A\n{section_a_lines}\n\n## Section B\n{section_b_lines}\n"
        chunks = parser.parse(
            content=md,
            file_path="docs/README.md",
            language="markdown",
            module_name="docs",
        )
        assert len(chunks) >= 2
