from datetime import datetime
from typing import List, Dict

MIN_R, MAX_R = 0.0, 5.0

class ValidationError(Exception): pass

def _dt(s: str):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except:
        try: return datetime(int(s[:4]), int(s[5:7]), 1)
        except: return None

def sanitize_and_validate_ratings(ratings: List[Dict], allow_empty: bool = True) -> List[Dict]:
    """Clamp rating [0,5], normalize course, drop dupes, validate essentials."""
    out, errs, seen = [], [], set()
    for i, r in enumerate(ratings or []):
        d = _dt(str(r.get("date","")))
        q = r.get("quality")
        try: q = None if q is None else max(MIN_R, min(MAX_R, float(q)))
        except: q = None
        c = (r.get("course") or "").strip() or "Unknown"
        key = (d and d.date().isoformat(), c, q)
        if key in seen: continue
        seen.add(key)
        out.append({"date": d and d.isoformat(), "quality": q, "course": c})
        if not d: errs.append(f"[{i}] bad date")
        if q is None: errs.append(f"[{i}] bad quality")
        if not isinstance(c, str): errs.append(f"[{i}] bad course")
    if errs or (not allow_empty and not out):
        raise ValidationError("\n".join(errs or ["no ratings"]))
    return out

def assert_valid_dataset(ds: List[Dict]) -> None:
    """Quick schema check for final JSON."""
    if not isinstance(ds, list): raise ValidationError("dataset not list")
    errs=[]
    for i,x in enumerate(ds):
        if not isinstance(x.get("professor"), str): errs.append(f"[{i}] professor missing")
        cst = x.get("course_semester_trends")
        if not isinstance(cst, list): errs.append(f"[{i}] course_semester_trends missing/list")
        else:
            for j,b in enumerate(cst):
                if not isinstance(b.get("course"), str): errs.append(f"[{i}][{j}] course missing")
                for k,t in enumerate(b.get("trend") or []):
                    try: float(t["avg_quality"]); int(t["count"]); assert isinstance(t["term"], str)
                    except: errs.append(f"[{i}][{j}][{k}] bad trend item")
    if errs: raise ValidationError("\n".join(errs))