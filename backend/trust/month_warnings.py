"""The month's warnings, and acknowledging them.

Warnings come from the checks at upload and from mapping notes. Each one can be acknowledged (who, when, why).
They gate nothing: there is no month lock (owner, 17 Nov 2026), so every month is always open and a
warning never stops an upload, a map, a score or a publish. Acknowledging only records that a person has read it.
"""
import hashlib
import re

from . import config, storage, store


def is_informational(note):
    """A mapping note that reports nothing wrong (owner, 5 Nov 2026): shown "for information", never
    acknowledged. Everything else is a warning."""
    m = re.match(r"(\d+) of (\d+) (?:Checkmarx|app inventory) repos matched to a GitHub repo", note)
    if m and m.group(1) == m.group(2):
        return True                                          # every repo matched: nothing to look at
    root = (config.settings().get("hr_root_sam_account") or "").strip().lower()
    if root and "has no L3 team owner above them" in note and note.rstrip(".").lower().endswith(root):
        return True                                          # the CTO has nobody above them by definition
    if note.startswith("For information: "):
        return True                                          # counts only (app inventory, owner 6 Nov 2026)
    m = re.match(r"(\d+) of (\d+) active apps? linked to an ITDR application", note)
    if m and m.group(1) == m.group(2):
        return True
    if note.startswith("Working rules until Change Management answers"):
        return True                                          # a standing note about the Non-TCC rules, not a finding
    return False


def warnings(month, include_info=False):
    """The month's warnings from its newest mapping, each with its acknowledgement (or None).
    Informational notes are left out unless include_info; with it, each carries info=True/False."""
    mapped = storage.load_month("mapped", month)
    if mapped is None:
        return []
    done, out = storage.acks(month), []
    pairs = [(feed, n) for feed, v in sorted(mapped["feeds"].items()) for n in v.get("notes") or []]
    pairs += [("general", n) for n in mapped.get("notes") or []]
    for feed, note in pairs:
        info = is_informational(note)
        if info and not include_info:
            continue
        key = hashlib.sha256(f"{feed}|{note}".encode()).hexdigest()[:16]
        out.append({"feed": feed, "note": note, "key": key, "ack": done.get(key), "info": info})
    return out


def acknowledge(month, keys, by, reason=""):
    """Acknowledge some of the month's current warnings, by key. Returns how many were newly acknowledged."""
    store.check_month(month)
    current = {w["key"]: w for w in warnings(month)}
    unknown = [k for k in keys if k not in current]
    if unknown:
        raise ValueError("Some of those warnings have changed since the page was loaded. Reload and try again.")
    n = 0
    for k in keys:
        w = current[k]
        if w["ack"] is None:
            storage.add_ack(month, w["feed"], k, w["note"], by, " ".join(str(reason or "").split()))
            n += 1
    if n:
        storage.log("acknowledge", by, month, f"{n} warning{'s' if n != 1 else ''}" + (f" ({reason})" if reason else ""),
                    {"keys": keys, "reason": reason})
    return n
