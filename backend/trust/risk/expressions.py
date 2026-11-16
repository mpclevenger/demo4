"""Reads one rule from a risk file and says whether it is met.

A risk file writes its rules as short text:

    RD02 in ad and RD54 in ad                  both drivers are on
    dc >= 1                                    at least one of the risk's drivers is on
    >.80 and (RD01 in ad or RD03 in ad)        driver share above 80%, and one of the two is on

The three things a rule can ask:

    RD02 in ad    is this driver on for the group?            ("ad" = the active drivers)
    dc >= 1       how many of the risk's own drivers are on?  ("dc" = driver count)
    >.80          is the driver share above this?             (share of the risk's likelihood drivers that are on)

joined with "and", "or" and brackets. "and" is worked out before "or", as in Python and in arithmetic
(multiply before add), so  A and B or C  means  (A and B) or C.

The text is read piece by piece. It is never run as code.
"""
import re

PIECE = re.compile(r"""\s*(?:
      (?P<open>\()                                                  # (
    | (?P<close>\))                                                 # )
    | (?P<and>and\b)                                                # and
    | (?P<or>or\b)                                                  # or
    | (?P<driver>RD\w+)\s+(?P<not>not\s+)?in\s+ad\b                 # RD02 in ad   /   RD02 not in ad
    | dc\s*(?P<count_sign>>=|<=|==|>|<)\s*(?P<count>\d+)            # dc >= 1
    | (?P<share_sign>>=|>)\s*(?P<share>\d+(?:\.\d+)?|\.\d+)         # >.80
    )""", re.X | re.I)

LONGEST_RULE = 500                                       # characters; the longest real rule is under 100
WHOLE_SHARE = 1.0                                        # a share runs from 0 to 1, so ">80" is a typo for ">.80"


def read_rule(text):
    """Turn the rule text into a tree of small steps. Raises ValueError, naming the place, when a piece
    of the text can't be read, so a typo in a risk file is caught when it is loaded."""
    text = str(text)
    if len(text) > LONGEST_RULE:
        raise ValueError(f"This rule is longer than {LONGEST_RULE} characters: {text[:60]!r}...")
    pieces = []
    at = 0
    while at < len(text):
        if text[at:].strip() == "":
            break
        found = PIECE.match(text, at)
        if not found:
            raise ValueError(f"Can't read this rule from character {at + 1}: {text!r}")
        pieces.append(found)
        at = found.end()
    if not pieces:
        raise ValueError("The rule is empty.")

    try:
        tree, used = _read_or(pieces, 0, text)
    except RecursionError:
        raise ValueError(f"This rule has too many brackets inside each other: {text[:60]!r}...") from None
    if used != len(pieces):
        raise ValueError(f"Something is left over at the end of this rule: {text!r}")
    return tree


def _read_or(pieces, i, text):
    """one-or-more 'and' groups joined by 'or'"""
    left, i = _read_and(pieces, i, text)
    while i < len(pieces) and pieces[i]["or"]:
        right, i = _read_and(pieces, i + 1, text)
        left = ("or", left, right)
    return left, i


def _read_and(pieces, i, text):
    """one-or-more single tests joined by 'and'"""
    left, i = _read_one(pieces, i, text)
    while i < len(pieces) and pieces[i]["and"]:
        right, i = _read_one(pieces, i + 1, text)
        left = ("and", left, right)
    return left, i


def _read_one(pieces, i, text):
    """a single test, or a bracketed group"""
    if i >= len(pieces):
        raise ValueError(f"This rule stops too early: {text!r}")
    piece = pieces[i]
    if piece["open"]:
        inside, i = _read_or(pieces, i + 1, text)
        if i >= len(pieces) or not pieces[i]["close"]:
            raise ValueError(f"A bracket is not closed in this rule: {text!r}")
        return inside, i + 1
    if piece["driver"]:
        kind = "driver_off" if piece["not"] else "driver_on"
        return (kind, piece["driver"].upper()), i + 1
    if piece["count"]:
        return ("driver_count", piece["count_sign"], int(piece["count"])), i + 1
    if piece["share"]:
        share = float(piece["share"])
        if share > WHOLE_SHARE:
            raise ValueError(f"A driver share is written from 0 to 1 (.80 for 80%), not {piece['share']}: {text!r}")
        return ("driver_share", piece["share_sign"], share), i + 1
    raise ValueError(f"This rule has a piece in the wrong place: {text!r}")


def compare(number, sign, limit):
    """Is `number` related to `limit` the way `sign` says (>=, >, <=, < or ==)?"""
    if sign == ">=":
        return number >= limit
    if sign == ">":
        return number > limit
    if sign == "<=":
        return number <= limit
    if sign == "<":
        return number < limit
    if sign == "==":
        return number == limit
    raise ValueError(f"Unknown sign in a rule: {sign!r}")


def rule_is_met(tree, active_drivers, driver_count, driver_share):
    """Is the rule met for this group?

    active_drivers  the drivers that are on for the group, e.g. {"RD01", "RD02"}
    driver_count    how many of this risk's own drivers are on
    driver_share    the share of this risk's likelihood drivers that are on, 0 to 1
    """
    step = tree[0]

    if step in ("and", "or"):
        left_side, right_side = tree[1], tree[2]
        left_is_met = rule_is_met(left_side, active_drivers, driver_count, driver_share)
        right_is_met = rule_is_met(right_side, active_drivers, driver_count, driver_share)
        return (left_is_met and right_is_met) if step == "and" else (left_is_met or right_is_met)

    if step in ("driver_on", "driver_off"):
        driver = tree[1]
        driver_is_on = driver in active_drivers
        return driver_is_on if step == "driver_on" else not driver_is_on

    if step == "driver_count":
        sign, limit = tree[1], tree[2]
        return compare(driver_count, sign, limit)

    if step == "driver_share":
        sign, limit = tree[1], tree[2]
        return compare(driver_share, sign, limit)

    raise ValueError(f"Unknown step in a rule: {step!r}")


def text_is_met(text, active_drivers, driver_count, driver_share):
    """Read the rule text and say whether it is met. An empty rule (null in the file) is never met."""
    if text is None or str(text).strip() == "":
        return False
    return rule_is_met(read_rule(text), active_drivers, driver_count, driver_share)


def drivers_named(text):
    """Every driver code the rule text mentions, so a rule naming a driver that doesn't exist can be listed."""
    if text is None:
        return set()
    return {found["driver"].upper() for found in PIECE.finditer(str(text)) if found["driver"]}
