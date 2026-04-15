"""Bundled compatibility shim for strategy imports.

This directory contains a copy of IMC Prosperity's `datamodel.py` so that uploaded
strategy files can resolve `from datamodel import ...` without any dependency on the
repo root. The strategy loader prepends this directory to sys.path at load time.
"""

from pathlib import Path

COMPAT_DIR: Path = Path(__file__).resolve().parent
