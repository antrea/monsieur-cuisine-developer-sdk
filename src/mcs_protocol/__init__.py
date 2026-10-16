"""Compatibility alias; implementation lives in the canonical MCS profile."""
import importlib
import sys

_canonical = importlib.import_module('monsieur_cuisine_sdk.profiles.mcs.protocol')
for _name in ('_baseline', 'types', 'schema', 'stream'):
    sys.modules[f'{__name__}.{_name}'] = importlib.import_module(f'{_canonical.__name__}.{_name}')
sys.modules[__name__] = _canonical
