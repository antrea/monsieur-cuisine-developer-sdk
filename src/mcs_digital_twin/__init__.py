"""Compatibility alias to the canonical headless MCS simulation, without a second GUI."""
import importlib
import sys

_canonical = importlib.import_module('monsieur_cuisine_sdk.profiles.mcs.simulation')
for _name in ('model', 'board', 'api', 'scenarios', 'limits'):
    sys.modules[f'{__name__}.{_name}'] = importlib.import_module(f'{_canonical.__name__}.{_name}')
sys.modules[__name__] = _canonical
