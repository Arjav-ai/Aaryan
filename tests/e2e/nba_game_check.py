import json, math, re, sys
sys.path.insert(0,"/home/user/aaryan/src")
from betsuggester import nba_game_model as M
data=json.load(open("/home/user/aaryan/data/predictions.json")); games={g["id"]:g for g in data["games"]}
dump=json.load(open("<output-folder>/nbadump.json")); bad=0
for d in dump:
    g=games[d["mid"]]["nba"]; mu_m,sd_m,mu_t,sd_t=g["mu_margin"],g["sd_margin"],g["mu_total"],g["sd_total"]
    if d["kind"]=="ml": ml=M.moneyline(mu_m,sd_m); win,push=ml[d["sel"]],0.0
    elif d["kind"]=="spr": win,push=M.spread(mu_m,d["line"],d["sel"],sd_m)
    else: win,push=M.total(mu_t,d["line"],d["sel"],sd_t)
    w=min(win,0.9); ev=w*d["odds"]+push-1
    sp=d["pct"].replace("%",""); shown=90 if "90" in d["pct"] and "+" in d["pct"] else (0 if "<1" in d["pct"] else int(sp))
    m=re.search(r"([+-]?\d+)% edge",d["edge"]); se=int(m.group(1)) if m else None
    ok=abs(shown-round(w*100))<=1 and se is not None and abs(se-round(ev*100))<=1
    bad+=not ok
    print("OK " if ok else "BAD",d["kind"],d["label"],"line",d["line"],"odds",d["odds"],"| page",shown,"% edge",se,"| python",round(w*100),"% edge",round(ev*100),"(push %.1f%%)"%(push*100))
print("mismatches:",bad,"of",len(dump))
