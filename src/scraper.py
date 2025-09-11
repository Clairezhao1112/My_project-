
import os, json, time, base64, requests
from datetime import datetime
from validators import sanitize_and_validate_ratings, assert_valid_dataset
from transformers import backoff, retry_on_requests_error, transform, llm_commentary

# RMP GraphQL endpoint + headers
URL = "https://www.ratemyprofessors.com/graphql"
SCHOOL_GID = base64.b64encode(b"School-675").decode()  # Relay id for NYU="school/675"
HDRS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://www.ratemyprofessors.com",
    "Referer": "https://www.ratemyprofessors.com/school/675",
    "Authorization": "Basic dGVzdDp0ZXN0",
}

TOP_PROFESSORS = 5       # how many professors to process
PROF_FETCH_LIMIT = 50    # how many professors to fetch from search
RATINGS_CAP = 300        # max reviews per professor

def gql(query, variables):
    r = requests.post(URL, json={"query": query, "variables": variables}, headers=HDRS, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "errors" in data: raise RuntimeError(data["errors"])
    return data.get("data", {})

@backoff(max_tries=6, base=0.6, factor=2, jitter=0.3, retry_if=retry_on_requests_error)
def gql(query, variables):
    r = requests.post(URL, json={"query": query, "variables": variables}, headers=HDRS, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "errors" in data: raise RuntimeError(data["errors"])
    return data.get("data", {})

# pick the most-rated professor to caclulate trends 
def get_professors(limit=50):
    q = """
    query Q($text:String!,$schoolID:ID!,$first:Int!,$after:String){
      search:newSearch{
        teachers(query:{text:$text,schoolID:$schoolID},first:$first,after:$after){
          edges{node{id firstName lastName avgRating numRatings}}
          pageInfo{hasNextPage endCursor}
        }
      }
    }"""
    out, after = [], None
    while len(out) < limit:
        d = gql(q, {"text":"", "schoolID":SCHOOL_GID, "first":min(25, limit-len(out)), "after":after})
        t = d.get("search",{}).get("teachers",{}) or {}
        for e in t.get("edges",[]):
            n = e["node"]
            out.append({
                "id": n["id"],
                "name": f'{(n.get("firstName") or "").strip()} {(n.get("lastName") or "").strip()}'.strip(),
                "avgRating": n.get("avgRating"),
                "numRatings": n.get("numRatings"),
            })
        if not t.get("pageInfo",{}).get("hasNextPage"): break
        after = t["pageInfo"]["endCursor"]; time.sleep(0.5)
    out.sort(key=lambda x: -(x["numRatings"] or 0))
    return out[:limit]

#Pull date, quality, and course for ratings 
def fetch_ratings(pid, cap=300):
    q = """
    query R($id:ID!,$first:Int!,$after:String){
      node(id:$id){
        ... on Teacher{
          ratings(first:$first,after:$after){
            edges{node{date qualityRating helpfulRating clarityRating class}}
            pageInfo{hasNextPage endCursor}
          }
        }
      }
    }"""
    res, after = [], None
    while len(res) < cap:
        d = gql(q, {"id":pid, "first":min(100, cap-len(res)), "after":after})
        r = d.get("node",{}).get("ratings",{}) or {}
        for e in r.get("edges",[]):
            n = e["node"]
            qv = n.get("qualityRating")
            if qv is None and n.get("helpfulRating") is not None and n.get("clarityRating") is not None:
                try: qv = (float(n["helpfulRating"]) + float(n["clarityRating"])) / 2.0
                except: qv = None
            res.append({"date": n.get("date"), "quality": qv, "course": (n.get("class") or "Unknown").strip() or "Unknown"})
        if not r.get("pageInfo",{}).get("hasNextPage"): break
        after = r["pageInfo"]["endCursor"]; time.sleep(0.5)
    return res

def term(dt: datetime):
    m = dt.month
    return (f"Spring {dt.year}" if m<=5 else f"Summer {dt.year}" if m<=8 else f"Fall {dt.year}")

def to_course_semester_trends(ratings):
    buckets = {}
    for r in ratings:
        ds, qv, course = r["date"], r["quality"], r["course"]
        if not ds or qv is None: continue
        try: dt = datetime.fromisoformat(ds.replace("Z","+00:00"))
        except: 
            try: dt = datetime(int(ds[:4]), int(ds[5:7]), 1)
            except: continue
        key = (course, term(dt))
        buckets.setdefault(key, []).append(float(qv))
    # group into {course: [{term, avg_quality, count}, ...]}
    tmp = {}
    for (course,tlabel), vals in buckets.items():
        tmp.setdefault(course, []).append({"term": tlabel, "avg_quality": round(sum(vals)/len(vals),2), "count": len(vals)})
    order = {"Spring":1,"Summer":2,"Fall":3}
    for course in tmp:
        tmp[course].sort(key=lambda x: (int(x["term"].split()[1]), order.get(x["term"].split()[0],9)))
    # flatten to list of course blocks
    return [{"course": c, "trend": tmp[c]} for c in sorted(tmp.keys())]

def main():
    print("Fetching professors…")
    profs = get_professors(PROF_FETCH_LIMIT)

    results, rows = [], []
    os.makedirs("data", exist_ok=True)

    for p in profs[:TOP_PROFESSORS]:
        print(f"- {p['name']} (ratings: {p['numRatings']})")

        # Fetch raw ratings
        raw = fetch_ratings(p["id"], RATINGS_CAP)

        # DATA QUALITY ASSURANCE: clamp to [0,5], parse dates, dedupe, validate each record
        ratings = sanitize_and_validate_ratings(raw, allow_empty=True)

        # BUSINESS LOGIC: build course×semester trends + value-added insights (slope, momentum, overall avg)
        res = transform(p["name"], ratings)
        res["current_rating"] = p["avgRating"]
        res["num_ratings"]    = p["numRatings"]

        results.append(res)

        # Build CSV rows from the transformed structure
        for block in res["course_semester_trends"]:
            for t in block["trend"]:
                rows.append([p["name"], block["course"], t["term"], t["avg_quality"], t["count"]])

        time.sleep(0.5)

    # Final dataset schema check (catches shape/type issues before writing)
    assert_valid_dataset(results)

    #EXPORT: JSON + CSV in ./data/
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    jpath = f"data/nyu_course_semester_trends_{ts}.json"
    with open(jpath,"w") as f: json.dump(results, f, indent=2)

    cpath = f"data/nyu_course_semester_trends_{ts}.csv"
    with open(cpath,"w") as f:
        f.write("professor,course,term,avg_quality,count\n")
        for r in rows: f.write(",".join(map(lambda x: str(x).replace(","," "), r))+"\n")

    print(f"\nSaved:\n- {jpath}\n- {cpath}")

if __name__ == "__main__":
    main()
