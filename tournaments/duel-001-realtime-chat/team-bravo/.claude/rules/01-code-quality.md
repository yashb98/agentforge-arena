# Code Quality
- ruff check + ruff format, zero tolerance for warnings
- Type hints mandatory — no implicit Any
- Functions ≤35 lines, files ≤250 lines
- All Pydantic models use ConfigDict(strict=True) for API boundaries
