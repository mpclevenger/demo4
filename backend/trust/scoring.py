"""Building-block and TRUST scores from metric statuses. The list of blocks comes from the page's data block
(`blocks`; each metric names its `block`), so adding a block is a data edit, not a code change.

Rules (docs/wiki/scoring-rules.md):
  - Points: Green 100, Amber 50, Red 0.
  - A block is the plain average of its scored metrics (owner, 9 Nov 2026: no weights),
    rounded to a whole number, half up (Decimal, ROUND_HALF_UP, D-04).
  - 'Info only' and 'Not Tier 0/1' are not applicable. 'DNR' (data not received) is left out
    and counted as missing (D-76). Other non-scored statuses ('N/A', 'Low confidence', ...)
    count as applicable but not scored.
  - A block needs at least `block_min_share` of the metrics that arrived to be scored (and always at least one),
    else 'Insufficient data'. Setting `coverage` in config/thresholds.json; 0 = any one scored metric (owner, 4 Nov 2026).
  - Caps (D-28, O-15): an automatic Red rule (metric override=True and Red) caps the block at 49;
    any Red metric caps the block at 79; any Red block caps the family TRUST at 79.
  - Family TRUST = average of the blocks' (capped) means, half up; needs at least `trust_min_blocks` scored blocks
    (setting `coverage`; 1 = any scored block, owner 4 Nov 2026).
  - Firm TRUST = the firm-wide metric results scored the same way (owner, 4 Nov 2026), see score_month.
  - Bands: 80+ Green, 50-79 Amber, below 50 Red.
"""
from decimal import Decimal, ROUND_HALF_UP

# The blocks as the page's data block lists them (code, name, question, provider, risk_category). Kept here as the
# default so the scorer works without a template; score_month passes the template's list.
BLOCKS = ['SEC', 'RES', 'STA', 'REL', 'ACC', 'MOD']
POINTS_BY_STATUS = {'Green': 100, 'Amber': 50, 'Red': 0}
SCORED_STATUSES = set(POINTS_BY_STATUS)     # statuses that carry points
NOT_APPLICABLE = ('Info only', 'Not Tier 0/1', 'Wanted')   # 'Wanted': no source yet (owner, 2 Nov 2026)
# The caps are settings (owner, 3 Nov 2026): config/thresholds.json "caps" overrides these defaults.
CAPS = {'automatic_red_block': 49, 'red_metric_block': 79, 'red_block_trust': 79}


# How much has to be measured before a block or TRUST is scored. These are the ORIGINAL rules (half the arrived
# metrics; 3 blocks). The live setting in config/thresholds.json "coverage" overrides them (owner, 4 Nov 2026: any
# one metric, any one block), so the live values are 0 and 1, not these. Do not change these defaults: tests rely on them.
COVERAGE = {'block_min_share': 0.5, 'trust_min_blocks': 3}


def coverage_from(cfg=None, blocks=None):
    """The coverage rules to use: the defaults, with any valid values given in cfg (a dict) in their place."""
    out = dict(COVERAGE)
    cfg = cfg or {}
    share = cfg.get('block_min_share')
    if isinstance(share, (int, float)) and not isinstance(share, bool) and 0 <= share <= 1:
        out['block_min_share'] = share
    fewest_blocks = cfg.get('trust_min_blocks')
    if isinstance(fewest_blocks, int) and not isinstance(fewest_blocks, bool) and 1 <= fewest_blocks <= len(blocks or BLOCKS):
        out['trust_min_blocks'] = fewest_blocks
    return out


def caps_from(cfg=None):
    """The caps to use: the defaults, with any whole numbers given in cfg (a dict) in their place."""
    out = dict(CAPS)
    for name, value in (cfg or {}).items():
        if name in out and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
            out[name] = value
    return out


def block_codes(metrics):
    """The block codes in use, in the order the metric list first names them (the template's order)."""
    seen = []
    for metric in metrics:
        code = metric.get('block')
        if code and code not in seen:
            seen.append(code)
    return seen or list(BLOCKS)


def round_half_up(number):
    """Round to a whole number, half up (D-04): 88.5 gives 89."""
    return int(Decimal(number).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def band(score):
    """Score band: 80+ Green, 50-79 Amber, below 50 Red."""
    return 'Green' if score >= 80 else 'Amber' if score >= 50 else 'Red'


def score_block(metric_results, caps=None, coverage=None):
    """Score one block. metric_results: list of (metric_id, metric_result). Returns (block_dict, mean or None)."""
    applicable = [(mid, result) for mid, result in metric_results if result['status'] not in NOT_APPLICABLE]
    missing = sum(1 for mid, result in applicable if result['status'] == 'DNR')      # D-76: not received -> left out, flagged "x of y metrics"
    received = [(mid, result) for mid, result in applicable if result['status'] != 'DNR']
    scored = [(mid, result) for mid, result in received if result['status'] in SCORED_STATUSES]
    red_count = sum(1 for mid, result in metric_results if result['status'] == 'Red')
    provisional = any(result.get('provisional') for mid, result in metric_results)
    base = dict(scored=len(scored), applicable=len(applicable), missing=missing, red_count=red_count,
                provisional=provisional, capped=False)

    if not applicable:                       # nothing applicable at all
        status = 'Not Tier 0/1' if any(result['status'] == 'Not Tier 0/1' for mid, result in metric_results) else 'N/A'
        return dict(base, score=None, status=status, scored=0, applicable=0), None
    if not received:                         # everything applicable is missing
        return dict(base, score=None, status='DNR', scored=0), None
    least_share = Decimal(str(coverage_from(coverage)['block_min_share']))
    if not scored or Decimal(len(scored)) / Decimal(len(received)) < least_share:   # coverage counted on what arrived (D-76)
        return dict(base, score=None, status='Insufficient data'), None

    mean = Decimal(sum(POINTS_BY_STATUS[result['status']] for mid, result in scored)) / Decimal(len(scored))
    score = round_half_up(mean)
    capped = False
    caps = caps_from(caps)
    automatic_red_cap, red_metric_cap = caps['automatic_red_block'], caps['red_metric_block']
    if any(result.get('override') and result['status'] == 'Red' for mid, result in scored) and score > automatic_red_cap:   # automatic Red rule
        score, mean, capped = automatic_red_cap, Decimal(automatic_red_cap), True
    if any(result['status'] == 'Red' for mid, result in scored) and score > red_metric_cap:                           # any Red metric (O-15)
        score, mean, capped = red_metric_cap, Decimal(red_metric_cap), True
    return dict(base, score=score, status=band(score), capped=capped), mean


def score_family(family_result, metrics, caps=None, coverage=None):
    """Score one family-month (or the firm, from its pooled results). family_result: {'metrics': {id: result}};
    metrics: the template's metric list, each with its 'block'.

    Returns (blocks dict, trust or None, status, capped).
    """
    blocks = {}
    means = []
    codes = block_codes(metrics)
    for code in codes:
        metric_results = [(metric['id'], family_result['metrics'][metric['id']]) for metric in metrics
                          if metric.get('block') == code and metric['id'] in family_result['metrics']]
        block_result, mean = score_block(metric_results, caps, coverage)
        blocks[code] = block_result
        if mean is not None:
            means.append(mean)
    if len(means) < coverage_from(coverage, codes)['trust_min_blocks']:
        return blocks, None, 'Insufficient data', False
    trust = round_half_up(sum(means, Decimal(0)) / len(means))
    capped = False
    red_block_cap = caps_from(caps)['red_block_trust']
    if any(result['status'] == 'Red' for result in blocks.values()) and trust > red_block_cap:
        trust, capped = red_block_cap, True
    return blocks, trust, band(trust), capped


def average_trust(trusts):
    """Average of the TRUST scores that exist, half up (the old firm rule; kept for the page's comparison line)."""
    existing = [trust for trust in trusts if trust is not None]
    return round_half_up(Decimal(sum(existing)) / len(existing)) if existing else None
