#!/bin/bash
ruff check "$1" --fix 2>/dev/null || true
