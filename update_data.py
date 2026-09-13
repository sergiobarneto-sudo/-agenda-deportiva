#!/usr/bin/env python3
import json, urllib.request, datetime
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Madrid")
NOW=datetime.datetime.now(datetime.timezone.utc)

DOMESTIC={
  "laliga":("LaLiga","esp.1","Movistar Plus+ / DAZN LALIGA · según partido",38),
  "premier":("Premier League","eng.1","DAZN",38),
  "bundesliga":("Bundesliga","ger.1","DAZN",34),
  "seriea":("Serie A","ita.1","DAZN",38),
  "ligue1":("Ligue 1","fra.1","DAZN",34),
}
EUROPE={
  "ucl":("UEFA Champions League","uefa.champions"),
  "uel":("UEFA Europa League","uefa.europa"),
  "uecl":("UEFA Conference League","uefa.europa.conf"),
}

SEASON_FROM="20260801"
SEASON_TO="20270630"

def get_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 agenda-deportiva"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

def iso_dt(s):
    return datetime.datetime.fromisoformat(s.replace("Z","+00:00"))

def status(ev):
    t=(ev.get("status") or {}).get("type") or {}
    state=(t.get("state") or "").lower()
    return bool(t.get("completed") or state=="post"), state=="in"

def week_of(ev):
    comp=(ev.get("competitions") or [{}])[0]
    week=(comp.get("week") or {}).get("number")
    if week is None:
        w=ev.get("week")
        week=w.get("number") if isinstance(w,dict) else w
    return week

def teams_scores(ev):
    comp=(ev.get("competitions") or [{}])[0]
    cs=comp.get("competitors") or []
    home=next((x for x in cs if x.get("homeAway")=="home"), cs[0] if cs else {})
    away=next((x for x in cs if x.get("homeAway")=="away"), cs[1] if len(cs)>1 else {})
    def nm(x):
        t=x.get("team") or {}
        return t.get("displayName") or t.get("shortDisplayName") or "Equipo"
    return nm(home),nm(away),home.get("score",""),away.get("score","")

def current_week(events):
    live=[e for e in events if status(e)[1] and week_of(e)]
    if live: return week_of(live[0])

    today=datetime.datetime.now(TZ).date()
    future=[]
    recent=[]
    for e in events:
        w=week_of(e)
        if not w: continue
        d=iso_dt(e["date"]).astimezone(TZ).date()
        completed,live=status(e)
        if not completed and d>=today-datetime.timedelta(days=1):
            future.append(((d-today).days,w))
        if completed:
            recent.append((abs((d-today).days),w))
    if future:
        future.sort(key=lambda x:x[0]); return future[0][1]
    if recent:
        recent.sort(key=lambda x:x[0]); return recent[0][1]
    return None

def event_obj(ev,key,league,tv=""):
    home,away,hs,as_=teams_scores(ev)
    completed,live=status(ev)
    st=ev.get("status") or {}
    comp=(ev.get("competitions") or [{}])[0]

    # ESPN dates far in the future can be placeholders. We keep them but mark as provisional
    # when no broadcast/details are known.
    broadcasts=comp.get("broadcasts") or []
    tv_name=""
    if broadcasts:
        names=[]
        for b in broadcasts:
            names.extend(b.get("names") or [])
        tv_name=" / ".join(dict.fromkeys(names))
    if not tv_name:
        tv_name=tv or ""

    return {
      "id":str(ev.get("id","")),
      "key":key,"league":league,"date":ev.get("date"),
      "round":week_of(ev),"home":home,"away":away,
      "homeScore":hs,"awayScore":as_,
      "completed":completed,"live":live,
      "clock":st.get("displayClock") or (st.get("type") or {}).get("shortDetail") or "",
      "tv":tv_name,
      "timeConfirmed": True if broadcasts or (iso_dt(ev["date"])-NOW).days < 45 else False
    }

def fetch_scoreboard(slug):
    url=f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={SEASON_FROM}-{SEASON_TO}"
    return (get_json(url).get("events") or [])

def domestic_data(key,name,slug,tv,max_rounds):
    events=fetch_scoreboard(slug)
    week=current_week(events)
    current=[]
    future=[]
    results=[]

    for e in events:
        obj=event_obj(e,key,name,tv)
        dt=iso_dt(e["date"])
        completed,live=status(e)

        # Resultados: solo finalizados/directo de la jornada actual.
        if (completed or live) and (week is None or obj["round"]==week):
            results.append(obj)

        # Ligas: nunca mostrar jornadas pasadas.
        if completed or live:
            continue

        # Jornada actual: partidos pendientes de esa jornada.
        if week is not None and obj["round"]==week:
            current.append(obj)
        else:
            # Futuras: desde la jornada siguiente hasta fin de temporada.
            if dt >= NOW-datetime.timedelta(hours=2):
                future.append(obj)

    current.sort(key=lambda x:x["date"])
    future.sort(key=lambda x:(x["round"] if isinstance(x["round"],int) else 999, x["date"]))
    results.sort(key=lambda x:x["date"])

    return {
      "name":name,
      "round":week,
      "results":results,
      "current":current,
      "future":future,
      # compatibilidad con versiones anteriores
      "upcoming":current+future
    }

def stat_value(stats,names):
    for n in names:
        for s in stats:
            if s.get("name")==n or s.get("abbreviation")==n:
                return s.get("value","")
    return ""

def standings(slug):
    urls=[
      f"https://site.api.espn.com/apis/v2/sports/soccer/{slug}/standings",
      f"https://site.web.api.espn.com/apis/v2/sports/soccer/{slug}/standings?region=es&lang=es"
    ]
    data=None
    for u in urls:
        try:
            data=get_json(u); break
        except Exception:
            pass
    if not data: return []

    groups=data.get("children") or []
    entries=[]
    if groups:
        for g in groups:
            e=((g.get("standings") or {}).get("entries") or [])
            if len(e)>len(entries): entries=e
    else:
        entries=((data.get("standings") or {}).get("entries") or [])

    out=[]
    for i,e in enumerate(entries):
        s=e.get("stats") or []
        team=e.get("team") or {}
        logos=team.get("logos") or []
        out.append({
          "pos":stat_value(s,["rank","RK"]) or i+1,
          "team":team.get("displayName") or team.get("shortDisplayName") or "Equipo",
          "logo":logos[0].get("href","") if logos else "",
          "pj":stat_value(s,["gamesPlayed","GP"]),
          "g":stat_value(s,["wins","W"]),
          "e":stat_value(s,["ties","draws","D"]),
          "p":stat_value(s,["losses","L"]),
          "gf":stat_value(s,["pointsFor","goalsFor","GF"]),
          "gc":stat_value(s,["pointsAgainst","goalsAgainst","GA"]),
          "dg":stat_value(s,["pointDifferential","goalDifference","GD"]),
          "pts":stat_value(s,["points","PTS"])
        })
    return out

out={
 "updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "domestic":{},"europe":{"upcoming":[]},"standings":{}
}

for key,(name,slug,tv,max_rounds) in DOMESTIC.items():
    try:
        out["domestic"][key]=domestic_data(key,name,slug,tv,max_rounds)
    except Exception as e:
        print("Domestic error",key,e)
        out["domestic"][key]={"name":name,"round":None,"results":[],"current":[],"future":[],"upcoming":[]}
    try:
        out["standings"][key]=standings(slug)
    except Exception as e:
        print("Standings error",key,e)
        out["standings"][key]=[]

euro=[]
for key,(name,slug) in EUROPE.items():
    try:
        events=fetch_scoreboard(slug)
        for e in events:
            obj=event_obj(e,key,name,"Movistar Plus+ / Orange TV · según partido")
            dt=iso_dt(e["date"])
            if not obj["completed"] and not obj["live"] and dt>=NOW-datetime.timedelta(hours=2):
                euro.append(obj)
    except Exception as e:
        print("Europe error",key,e)
    try:
        out["standings"][key]=standings(slug)
    except Exception as e:
        print("Europe standings error",key,e)
        out["standings"][key]=[]

euro.sort(key=lambda x:x["date"])
out["europe"]["upcoming"]=euro

with open("data.json","w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,separators=(",",":"))
print("Updated data.json at",out["updated_at"])
