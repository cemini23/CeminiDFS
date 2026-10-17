"""Situational telemetry for GPP ceilings and stack correlations.

Public entry points live in the submodules. This package does not fetch data
on import.
"""

from ceminidfs.situational.lag import cut_point_in_time

__all__ = ["cut_point_in_time"]
