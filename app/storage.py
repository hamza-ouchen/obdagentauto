"""SQLite embarqué : fiches, données OBDb, dossiers, traces et réservations."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo
from app.data import DEMO_CODES

SEED = Path(__file__).parent / "seed"


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS kb_codes(code TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS vehicles(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS diagnostics(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,agent TEXT,kind TEXT,timestamp TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,run_id TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS appointments(id TEXT PRIMARY KEY,run_id TEXT UNIQUE,slot TEXT UNIQUE,payload TEXT);
        """)
        with self.db:
            for code, entry in DEMO_CODES.items():
                self.db.execute("INSERT OR IGNORE INTO kb_codes VALUES (?,?)", (code, json.dumps(entry, ensure_ascii=False)))
            for slug, label in [("toyota-corolla-hybrid", "Toyota Corolla Hybrid"), ("honda-civic", "Honda Civic")]:
                source = json.loads((SEED / "obdb" / f"{slug}.source.json").read_text(encoding="utf-8"))
                raw = json.loads((SEED / "obdb" / f"{slug}.json").read_text(encoding="utf-8-sig"))
                signals = [{"id": s["id"], "name": s.get("name",s["id"]), "unit": s.get("fmt",{}).get("unit","scalar"), "filter": cmd.get("filter",{}), "path": s.get("path",""), "source": source} for cmd in raw.get("commands",[]) if not cmd.get("dbg") for s in cmd.get("signals",[])]
                self.db.execute("INSERT OR REPLACE INTO vehicles VALUES (?,?)", (slug,json.dumps({"id":slug,"name":label,"source":source,"signals":signals},ensure_ascii=False)))

    def close(self):
        self.db.close()

    def code(self, code):
        with self.lock:
            row = self.db.execute("SELECT payload FROM kb_codes WHERE code=?",(code,)).fetchone()
        return json.loads(row[0]) if row else None

    def codes(self):
        with self.lock:
            rows = self.db.execute("SELECT code,payload FROM kb_codes ORDER BY code").fetchall()
        return [{"code":r[0],**json.loads(r[1])} for r in rows]

    @staticmethod
    def applicable(rule, year):
        if year is None:
            return not rule
        return (not rule.get("from") or year>=rule["from"]) and (not rule.get("to") or year<=rule["to"]) and (not rule.get("years") or year in rule["years"])

    def vehicles(self, year=None, vehicle_id=None):
        with self.lock:
            rows=self.db.execute("SELECT payload FROM vehicles ORDER BY id").fetchall()
        result=[json.loads(r[0]) for r in rows]
        if vehicle_id:
            result=[v for v in result if v["id"]==vehicle_id]
        for v in result:
            v["signals"]=[s for s in v["signals"] if self.applicable(s["filter"],year)]
        return result

    def create(self, payload):
        with self.lock,self.db:
            self.db.execute("INSERT INTO diagnostics VALUES (?,?)",(payload["id"],json.dumps(payload,ensure_ascii=False)))

    def get(self, run_id):
        with self.lock:
            row=self.db.execute("SELECT payload FROM diagnostics WHERE id=?",(run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def merge(self, run_id, changes):
        with self.lock,self.db:
            data=self.get(run_id)
            data.update(changes,updated_at=utcnow())
            self.db.execute("UPDATE diagnostics SET payload=? WHERE id=?",(json.dumps(data,ensure_ascii=False),run_id))
        return data

    def runs(self):
        with self.lock:
            rows=self.db.execute("SELECT payload FROM diagnostics ORDER BY rowid DESC LIMIT 500").fetchall()
        return [json.loads(r[0]) for r in rows]

    def event(self, run_id, agent, kind, **payload):
        timestamp=utcnow()
        with self.lock,self.db:
            cur=self.db.execute("INSERT INTO events(run_id,agent,kind,timestamp,payload) VALUES (?,?,?,?,?)",(run_id,agent,kind,timestamp,json.dumps(payload,ensure_ascii=False)))
        return {"id":cur.lastrowid,"correlation_id":run_id,"agent":agent,"kind":kind,"timestamp":timestamp,**payload}

    def events(self, run_id=None, after=0):
        with self.lock:
            rows=self.db.execute("SELECT * FROM events WHERE id>? AND (? IS NULL OR run_id=?) ORDER BY id",(after,run_id,run_id)).fetchall()
        return [{"id":r["id"],"correlation_id":r["run_id"],"agent":r["agent"],"kind":r["kind"],"timestamp":r["timestamp"],**json.loads(r["payload"])} for r in rows]

    def incident(self, run_id, agent, category, simulated=False):
        data={"id":uuid4().hex,"correlation_id":run_id,"agent":agent,"category":category,"simulated":simulated,"status":"detected","runbook":"RB-LLM-01","created_at":utcnow(),"actions":["Erreur fournisseur détectée"]}
        with self.lock,self.db:
            self.db.execute("INSERT INTO incidents VALUES (?,?,?)",(data["id"],run_id,json.dumps(data,ensure_ascii=False)))
        return data

    def mitigate(self, incident):
        incident.update(status="mitigated",actions=incident["actions"]+["Fiche SQLite disponible vérifiée","Repli local appliqué","Parcours poursuivi sans réservation automatique"])
        with self.lock,self.db:
            self.db.execute("UPDATE incidents SET payload=? WHERE id=?",(json.dumps(incident,ensure_ascii=False),incident["id"]))

    def incidents(self):
        with self.lock:
            rows=self.db.execute("SELECT payload FROM incidents ORDER BY rowid DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def slots(self):
        now=datetime.now(ZoneInfo("Africa/Casablanca"))
        with self.lock:
            booked={r[0] for r in self.db.execute("SELECT slot FROM appointments")}
        result=[]
        for offset in range(1,15):
            day=now+timedelta(days=offset)
            if day.weekday()<5:
                for h in (9,11,14):
                    slot=day.replace(hour=h,minute=0,second=0,microsecond=0).isoformat()
                    if slot not in booked:
                        result.append(slot)
        return result

    def book(self, run_id, slot):
        with self.lock,self.db:
            existing=self.db.execute("SELECT payload FROM appointments WHERE run_id=?",(run_id,)).fetchone()
            if existing:
                appointment=json.loads(existing[0])
                if appointment["slot"]!=slot:
                    raise ValueError("Ce dossier possède déjà une réservation.")
                return appointment
            if slot not in self.slots():
                raise ValueError("Ce créneau n’est plus disponible.")
            run=self.get(run_id)
            data={"id":uuid4().hex[:12].upper(),"correlation_id":run_id,"slot":slot,"workshop":"AutoDiag Atelier · Casablanca","code":run["code"],"vehicle":run["vehicle"],"total":run["estimate"]["total"],"confirmed":True}
            self.db.execute("INSERT INTO appointments VALUES (?,?,?,?)",(data["id"],run_id,slot,json.dumps(data,ensure_ascii=False)))
            return data

    def appointments(self):
        with self.lock:
            rows=self.db.execute("SELECT payload FROM appointments ORDER BY slot").fetchall()
        return [json.loads(r[0]) for r in rows]
