"""Why does an L3 team score the way it does? Prints, for one month and one team, where its rows came from.

    python tools/why_family.py 2026-11 payments

Shows: the team's lead and people, how many rows of each file were placed with the team, each metric's
counts, the scored result for each metric with its reason, and the coverage settings that decide whether a building block and TRUST get a score. Reads only; changes nothing.
Run it from the repo root after Update the scorecard (or map + score) for the month.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import measure, score_month, storage  # noqa: E402


def main(month, fid):
    mapped = storage.load_month("mapped", month)
    if not mapped:
        sys.exit(f"{month} hasn't been mapped yet: press Update the scorecard (or run python manage.py map {month}).")
    feeds = mapped["feeds"]
    hm = feeds.get("teams") or {}
    fam = next((f for f in hm.get("families") or [] if f.get("family_id") == fid), None)
    known = [f.get("family_id") for f in hm.get("families") or []]
    if not fam:
        sys.exit(f"No L3 team '{fid}' for {month}. Family ids: {', '.join(known)}")
    print(f"== {fam.get('family')} ({fid}), {month}")
    info = storage.run_info("mapped", month) or {}
    now_sha = storage.git_sha() or ""
    print(f"last mapped: {info.get('at', '?')} by {info.get('by', '?')} | code that mapped it: "
          f"{(info.get('git_sha') or '')[:10] or 'not recorded'} | code running now: {now_sha[:10] or 'not recorded'}"
          f" | database: {'yes' if storage.using_database() else 'NO (reading the local store folder)'}")
    from trust import config, linking
    st = config.settings()
    print(f"settings: l3_level = {linking.l3_level(st)} | hr_root_sam_account set: {bool(st.get('hr_root_sam_account'))}")
    ups = [e for e in storage.events(month, 400) if str(e.get("action", "")).startswith("update ")][:6]
    if ups:
        print("recent Update attempts (newest first):")
        for e in ups:
            print(f"   {e['at'][:19]}  {e['action']}  {str(e.get('note') or '')[:160]}")
        if ups[0]["action"] != "update finished":
            print("   -> the newest Update didn't finish, so the month still shows an earlier result. "
                  f"Run python manage.py map {month} in the shell to see the error.")
    print(f"leads: {', '.join(fam.get('owner_emails') or [])} | people placed: {fam.get('people')}")
    ppl = feeds.get("hr", {}).get("people") or []
    if ppl and not any("family_id" in p for p in ppl):
        print("HR people: no family recorded on them: this month was mapped before families were placed, or with older "
              f"code. Run python manage.py map {month}.")
    print(f"HR people with this team's key: {sum(1 for p in ppl if p.get('family_id') == fid)}")
    print("\n-- rows placed per file (this team / not yet mapped / whole file)")
    for name, f in sorted(feeds.items()):
        rows = f.get("rows")
        if not isinstance(rows, list) or not rows or not any(isinstance(r, dict) and "family_id" in r for r in rows[:500]):
            continue
        c = lambda k: sum(1 for r in rows if r.get("family_id") == k)
        print(f"{name:20} {c(fid):6} / {c('UNATTRIBUTED'):6} / {len(rows):6}")
    meas = measure.measure(mapped)
    print("\n-- counts per metric: numerator / denominator")
    for mid in sorted(meas["counts"]):
        raw = meas["counts"][mid]
        own = raw.get(fid) or {}
        nd = lambda c: f"{c.get('numerator', 0)}/{c.get('denominator', '-')}"
        print(f"{mid:6} {nd(own):>10}   {'received' if mid in meas['received'] else 'file not received'}")
    sc = storage.load_month("scored", month)
    fr = ((sc or {}).get("period") or {}).get("families", {}).get(fid)
    if not fr:
        print(f"\nNot scored yet: run python manage.py score {month}")
        return
    print(f"\n-- scored: TRUST {fr.get('trust')} ({fr.get('status')}); blocks: "
          + ", ".join(f"{b} {x.get('score')}" for b, x in fr["blocks"].items()))
    for mid, r in sorted(fr["metrics"].items()):
        print(f"{mid:6} {str(r.get('status')):14} value {r.get('value')}  | {r.get('reason') or ''}"[:220])
    cfg = score_month.thresholds_config()
    cov = (sc["period"].get("coverage") or cfg.get("coverage") or {})
    print(f"\ncoverage used: {cov or 'code defaults (a block needs half its metrics, TRUST needs 3 blocks)'}"
          f" | switched on: {cfg.get('switched_on')}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
