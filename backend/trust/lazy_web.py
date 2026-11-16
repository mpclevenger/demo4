"""Gives the Risk, editing and metric intake routes TRUST's web.py (for require, Refused, NotAllowed and _who).

web.py imports those routes while it is still loading, so they can't import web.py at the top of their own files.
They call trust_web() when a request arrives instead.
"""
from flask import g

from trust import access


def trust_web():
    from trust import web
    return web


def stop_data_senders():
    """Run before every Risk and editing route: a team's service account that only sends metric numbers has no
    business there."""
    if access.is_only_a_data_sender(g.person):
        raise trust_web().NotAllowed()
