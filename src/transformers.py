# transformer.py
import os, time, random
from datetime import datetime
from typing import List, Dict

SEAS = {"Spring":1,"Summer":2,"Fall":3}

# Respectful scraping: exponential backoff + retry limit
def backoff(max_tries=5, base=0.5, factor=2.0, jitter=0.25, retry_if=None):
    def wrap(fn):
        def run(*a, **kw):
            d=base; last=None
            for i in range(1, max_tries+1):
                try: return fn(*a, **kw)
                except Exception as e:
                    if retry_if and not retry_if(e): raise
                    last=e
                    if i==max_tries: break
                    time.sleep(d + (random.random()-0.5)*2*jitter); d*=factor
            raise last
        return run
    return wrap

def retry_on_requests_error(e: Exception) -> bool:
    s = repr(e); code = getattr(getattr(e, "response", None), "status_code", 0)
    return any(t in s for t in ("Timeout","ConnectionError","HTTPError","ReadTimeout")) or code in (429,500,502,503,504)

# Business logic: transform to course x semester trends + insights 
def _dt(s):
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except:
        try: return datetime(int(s[:4]), int(s[5:7]), 1)
        except: return None

def _term(dt):
    m=dt.month
    return f"Spring {dt.year}" if m<=5 else f"Summer {dt.year}" if m<=8 else f"Fall {dt.year}"

def course_semester_trends(ratings: List[Dict]) -> List[Dict]:
    buckets={}
    for r in ratings:
        dt=_dt(r.get("date")); q=r.get("quality"); c=(r.get("course") or "Unknown").strip() or "Unknown"
        if not dt or q is None: continue
        buckets.setdefault((c,_term(dt)), []).append(float(q))
    per_course={}
    for (c,t),vals in buckets.items():
        per_course.setdefault(c,[]).append({"term":t,"avg_quality":round(sum(vals)/len(vals),2),"count":len(vals)})
    def key(term): s,y=term.split(); return (int(y), SEAS.get(s,9))
    return [{"course":c,"trend":sorted(ts,key=lambda x:key(x["term"]))} for c,ts in sorted(per_course.items())]

def _slope(tr):
    # tiny least-squares slope on term index
    def ti(t): s,y=t.split(); return int(y)*3+SEAS.get(s,0)
    pts=[(ti(x["term"]), float(x["avg_quality"])) for x in tr]
    n=len(pts)
    if n<2: return 0.0
    sx=sum(x for x,_ in pts); sy=sum(y for _,y in pts)
    sxx=sum(x*x for x,_ in pts); sxy=sum(x*y for x,y in pts)
    den=n*sxx-sx*sx
    return 0.0 if not den else round((n*sxy - sx*sy)/den,4)

def transform(professor: str, ratings: List[Dict]) -> Dict:
    blocks=course_semester_trends(ratings)
    for b in blocks:
        b["slope"]=_slope(b["trend"])
        b["momentum"]=round((b["trend"][-1]["avg_quality"]-b["trend"][-2]["avg_quality"]) if len(b["trend"])>=2 else 0.0,2)
    ws=n=0
    for b in blocks:
        if b["trend"]:
            last=b["trend"][-1]; ws+=last["avg_quality"]*last["count"]; n+=last["count"]
    return {
        "professor": professor,
        "course_semester_trends": blocks,
        "insights": {
            "best_course": max(blocks, key=lambda b:(b["trend"][-1]["avg_quality"] if b["trend"] else -1)).get("course") if blocks else None,
            "most_improved": max(blocks, key=lambda b:b.get("slope",0)).get("course") if blocks else None,
            "overall_recent_avg": round(ws/n,2) if n else None
        }
    }

def llm_commentary(summary: Dict):
    """Optional one-liner via OpenAI; returns None if unavailable."""
    key=os.getenv("OPENAI_API_KEY")
    if not key: return None
    try:
        from openai import OpenAI
        c=OpenAI(api_key=key)
        r=c.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":f"One 25-word neutral insight about:\n{summary}"}],
            max_tokens=60, temperature=0.3,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return None