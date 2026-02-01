#!/usr/bin/env python3
"""Thin wrapper: run pygit CLI. Usage: python main.py <cmd> ... (same as python -m pygit)."""

import sys

if __name__ == "__main__":
    from pygit.cli import main
    sys.exit(main())
