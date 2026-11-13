import json, urllib.request, collections
BBOX = "3.8,36.3,7.2,37.1"
rows = []
for cid, label in [("C2854338529-ASF", "PROV"), ("C3622241360-ASF", "VALID")]:
    url = ("https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=%s"
           "&bounding_box=%s&temporal=2025-10-01T00:00:00Z,2026-11-09T23:59:59Z&page_size=200&sort_key=start_date" % (cid, BBOX))
    d = json.load(urllib.request.urlopen(url))
    for it in d["items"]:
        u = it["umm"]
        aa = {a["Name"]: a["Values"] for a in u.get("AdditionalAttributes", [])}
        pts = u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
        lons = [p["Longitude"] for p in pts]; lats = [p["Latitude"] for p in pts]
        size = None
        for a in u.get("DataGranule", {}).get("ArchiveAndDistributionInformation", []):
            if a.get("Name", "").endswith(".h5"):
                size = a.get("SizeInBytes") or a.get("Size")
        rows.append(dict(label=label, date=u["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:16],
                         stack=aa.get("STACK_ID", ["?"])[0], pol="+".join(aa.get("FREQUENCY_A_POLARIZATION", [])),
                         bw=aa.get("RANGE_BANDWIDTH_CONCAT", ["?"])[0], full=aa.get("FULL_FRAME", ["?"])[0],
                         bbox=(round(min(lons),2), round(min(lats),2), round(max(lons),2), round(max(lats),2)),
                         size=size, ur=u["GranuleUR"],
                         urls=[r["URL"] for r in u.get("RelatedUrls", []) if r["URL"].endswith(".h5")]))
json.dump(rows, open("passes.json", "w"), indent=1)
by = collections.defaultdict(list)
for r in rows: by[r["stack"]].append(r)
for s, rs in sorted(by.items()):
    print("\nSTACK %s  bbox %s  n=%d  pols=%s  bw=%s" % (s, rs[0]["bbox"], len(rs), sorted({r["pol"] for r in rs}), sorted({r["bw"] for r in rs})))
    for r in rs:
        print("  %s %s %s size=%s full=%s" % (r["date"], r["label"], r["pol"], ("%.2f GB" % (r["size"]/1e9)) if isinstance(r["size"], (int, float)) else r["size"], r["full"]))
print("\nexample urls:", rows[0]["urls"])
