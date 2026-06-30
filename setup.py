# Shim so `pip install -e .` works on servers with an older setuptools (<64) that
# lacks the PEP 660 build_editable hook: its presence lets pip fall back to the
# legacy editable install. All real metadata lives in pyproject.toml.
from setuptools import setup

setup()
