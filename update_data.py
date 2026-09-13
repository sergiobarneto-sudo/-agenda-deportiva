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
    def lg(x):
        t=x.get("team") or {}
        logos=t.get("logos") or []
        if logos:
            first=logos[0]
            if isinstance(first,dict):
                return first.get("href","")
            return first
        return ""
    return nm(home),nm(away),home.get("score",""),away.get("score",""),lg(home),lg(away)

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

SPANISH_TEAMS = {
    "Real Madrid","FC Barcelona","Barcelona","Atletico Madrid","Atlético Madrid",
    "Real Sociedad","Real Sociedad San Sebastian","Athletic Bilbao","Villarreal CF","Real Betis Seville",
    "Sevilla FC","Valencia CF","RC Celta de Vigo","Getafe CF","Levante UD","CA Osasuna",
    "Rayo Vallecano","Elche CF","Espanyol Barcelona","Malaga CF","RC Deportivo de A Coruna",
    "Deportivo Alaves","Racing Santander"
}

def event_obj(ev,key,league,tv=""):
    home,away,hs,as_,home_logo,away_logo=teams_scores(ev)
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
      "timeConfirmed": True if broadcasts or (iso_dt(ev["date"])-NOW).days < 45 else False,
      "homeLogo":home_logo,
      "awayLogo":away_logo,
      "spanishTeamHome": home in SPANISH_TEAMS,
      "spanishTeamAway": away in SPANISH_TEAMS
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


# ---------------- MOTOR ----------------
def parse_ergast_iso(date_s,time_s):
    if not date_s:
        return None
    t=time_s or "00:00:00Z"
    return f"{date_s}T{t.replace('Z','+00:00')}"

def f1_data():
    base="https://api.jolpi.ca/ergast/f1/2026"
    sched=get_json(base+".json")
    races=(((sched.get("MRData") or {}).get("RaceTable") or {}).get("Races") or [])

    now=NOW
    events=[]
    for r in races:
        sessions=[]
        parts=[
          ("FirstPractice","Entrenamientos libres 1"),
          ("SecondPractice","Entrenamientos libres 2"),
          ("ThirdPractice","Entrenamientos libres 3"),
          ("SprintQualifying","Clasificación Sprint"),
          ("Sprint","Sprint"),
          ("Qualifying","Clasificación"),
        ]
        for key,label in parts:
            x=r.get(key)
            if x and x.get("date"):
                iso=parse_ergast_iso(x.get("date"),x.get("time"))
                dt=iso_dt(iso) if iso else None
                status_s="completed" if dt and dt < now else "scheduled"
                sessions.append({"name":label,"date":iso,"status":status_s,"tv":"DAZN F1","result":""})
        race_iso=parse_ergast_iso(r.get("date"),r.get("time"))
        if race_iso:
            dt=iso_dt(race_iso)
            sessions.append({
              "name":"Carrera","date":race_iso,
              "status":"completed" if dt < now else "scheduled",
              "tv":"DAZN F1" + (" · Telecinco / Mediaset" if "spain" in (r.get("raceName","").lower()) else ""),
              "result":""
            })

        # keep current and future weekends only
        if sessions:
            last=max(iso_dt(s["date"]) for s in sessions if s.get("date"))
            if last >= now-datetime.timedelta(days=2):
                events.append({
                  "name":r.get("raceName","Gran Premio"),
                  "circuit":((r.get("Circuit") or {}).get("circuitName") or ""),
                  "round":r.get("round"),
                  "sessions":sessions
                })

    driver=[]
    try:
        j=get_json(base+"/driverstandings.json")
        lists=((((j.get("MRData") or {}).get("StandingsTable") or {}).get("StandingsLists")) or [])
        for row in (lists[0].get("DriverStandings") if lists else []) or []:
            d=row.get("Driver") or {}
            constructors=row.get("Constructors") or []
            driver.append({
              "position":row.get("position",""),
              "name":f"{d.get('givenName','')} {d.get('familyName','')}".strip(),
              "team":constructors[0].get("name","") if constructors else "",
              "points":row.get("points","")
            })
    except Exception as e:
        print("F1 driver standings error",e)

    constructors_out=[]
    try:
        j=get_json(base+"/constructorstandings.json")
        lists=((((j.get("MRData") or {}).get("StandingsTable") or {}).get("StandingsLists")) or [])
        for row in (lists[0].get("ConstructorStandings") if lists else []) or []:
            c=row.get("Constructor") or {}
            constructors_out.append({
              "position":row.get("position",""),
              "name":c.get("name",""),
              "points":row.get("points","")
            })
    except Exception as e:
        print("F1 constructor standings error",e)

    return {"events":events,"driverStandings":driver,"constructorStandings":constructors_out}

MOTOGP_SESSION_NAMES={
  "FP":"Entrenamientos libres","FP1":"Entrenamientos libres 1","FP2":"Entrenamientos libres 2",
  "P":"Práctica","PR":"Práctica","Q":"Clasificación","Q1":"Clasificación Q1","Q2":"Clasificación Q2",
  "SPR":"Sprint","SPRINT":"Sprint","WUP":"Warm Up","RAC":"Carrera","RACE":"Carrera"
}

def motogp_data():
    base="https://api.motogp.pulselive.com/motogp/v1"
    seasons=get_json(base+"/results/seasons")
    season=next((s for s in seasons if int(s.get("year",0))==2026),None)
    if not season:
        return {"events":[],"riderStandings":[]}
    sid=season.get("id")

    cats=get_json(base+f"/results/categories?seasonUuid={sid}")
    cat=next((c for c in cats if c.get("legacy_id")==3 or "MotoGP" in c.get("name","")),None)
    if not cat:
        return {"events":[],"riderStandings":[]}
    cid=cat.get("id")

    events_raw=get_json(base+f"/results/events?seasonUuid={sid}")
    events=[]
    for ev in events_raw:
        eid=ev.get("id")
        if not eid: continue
        try:
            sessions=get_json(base+f"/results/sessions?eventUuid={eid}&categoryUuid={cid}")
        except Exception as e:
            print("MotoGP sessions error",eid,e)
            sessions=[]

        sess_out=[]
        for s in sessions:
            iso=s.get("date")
            if not iso: continue
            dt=iso_dt(iso)
            typ=(s.get("type") or "").upper()
            label=MOTOGP_SESSION_NAMES.get(typ,typ or "Sesión")
            status_raw=(s.get("status") or "").lower()
            if "live" in status_raw or "current" in status_raw:
                stat="live"
            elif dt < NOW and ("official" in status_raw or "finished" in status_raw or "final" in status_raw):
                stat="completed"
            elif dt < NOW:
                stat="completed"
            else:
                stat="scheduled"
            sess_out.append({
              "name":label,"date":iso,"status":stat,
              "tv":"DAZN / Movistar Plus+","result":""
            })

        # only current/future events; if sessions not published use event dates when possible
        if sess_out:
            last=max(iso_dt(s["date"]) for s in sess_out)
            if last < NOW-datetime.timedelta(days=2):
                continue
        else:
            # keep events explicitly current/future if API status says so
            st=(ev.get("status") or "").upper()
            if st not in ("CURRENT","UPCOMING","FUTURE"):
                continue

        events.append({
          "name":ev.get("sponsored_name") or ev.get("name") or ((ev.get("country") or {}).get("name") or "Gran Premio"),
          "circuit":((ev.get("circuit") or {}).get("name") or ""),
          "sessions":sorted(sess_out,key=lambda x:x.get("date") or "")
        })

    events.sort(key=lambda ev: ev["sessions"][0]["date"] if ev.get("sessions") else "9999")

    riders=[]
    try:
        st=get_json(base+f"/results/standings?seasonUuid={sid}&categoryUuid={cid}")
        for row in st.get("classification") or []:
            rider=row.get("rider") or {}
            team=row.get("team") or {}
            riders.append({
              "position":row.get("position",""),
              "name":rider.get("full_name",""),
              "team":team.get("name",""),
              "points":row.get("points","")
            })
    except Exception as e:
        print("MotoGP standings error",e)

    return {"events":events,"riderStandings":riders}


out={
 "updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "domestic":{},"europe":{"upcoming":[]},"standings":{},"motor":{"f1":{},"motogp":{}}
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
                obj["spanishTeam"]=bool(obj.get("spanishTeamHome") or obj.get("spanishTeamAway"))
                obj["seeded"]=False
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


try:
    out["motor"]["f1"]=f1_data()
except Exception as e:
    print("F1 data error",e)
    out["motor"]["f1"]={"events":[],"driverStandings":[],"constructorStandings":[]}

try:
    out["motor"]["motogp"]=motogp_data()
except Exception as e:
    print("MotoGP data error",e)
    out["motor"]["motogp"]={"events":[],"riderStandings":[]}

with open("data.json","w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,separators=(",",":"))
print("Updated data.json at",out["updated_at"])
