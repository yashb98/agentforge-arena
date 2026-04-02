#!/bin/bash
ruff format "$1" 2>/dev/null || true
