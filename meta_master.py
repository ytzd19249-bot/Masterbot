#!/usr/bin/env python3
# meta_master.py — Creador/Deployer de bots (uno por uno): GitHub + Render
# Uso:
#   export GITHUB_TOKEN=xxxx
#   export GITHUB_USERNAME=tu_usuario
#   export RENDER_API_KEY=xxxx           # (opcional pero recomendado)
#   export RENDER_OWNER_ID=xxxx          # (ID de tu cuenta/equipo en Render)
#   python meta_master.py --name jaguar --bot_id 1 --pair BTC/USDT --strategy combo --timeframe 1m

import os, json, subprocess, base64, time, textwrap
from pathlib import Path
from dataclasses import dataclass
import requests

# ========= Config tokens (desde el entorno) =========
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN","")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME","")
RENDER_API_KEY  = os.getenv("RENDER_API_KEY","")
RENDER_OWNER_ID = os.getenv("RENDER_OWNER_ID","")  # tu user/team id en Render

# ========= Plantillas mínimas (trading avanzado — paper por defecto) =========
REQS = """\
fastapi
uvicorn
ccxt
pandas
pandas_ta
SQLAlchemy
pydantic
httpx
"""

DOCKERFILE = """\
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV PORT=8000
CMD ["python","main.py","--worker"]
"""

MAIN_PY = """\
import os, asyncio
from datetime import datetime
from fastapi import FastAPI
from strategies import DataFeed, signal_combo, signal_ema, signal_rsi_macd, signal_scalping
from exchange import PaperExchange, RealExchange
from storage import init_db, record_trade, fetch_bot_stats, update_bot_stats

BOT_ID = os.getenv("BOT_ID", "{bot_id}")
PAIR = os.getenv("PAIR", "{pair}")
STRATEGY = os.getenv("STRATEGY", "{strategy}")
TIMEFRAME = os.getenv("TIMEFRAME", "{timeframe}")
MODE = os.getenv("MODE", "paper")  # paper | real
SIZE_PCT = float(os.getenv("SIZE_PCT", "0.12"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.006"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.012"))
TRAILING_PCT = float(os.getenv("TRAILING_PCT", "0.004"))
MAX_OPEN_TIME_SEC = int(os.getenv("MAX_OPEN_TIME_SEC", "3600"))
LOOP_SECONDS = int(os.getenv("LOOP_SECONDS", "7"))
BASE_CAPITAL = float(os.getenv("BASE_CAPITAL", "1000"))
ADAPTIVE = os.getenv("ADAPTIVE","1") == "1"
MAX_CONSEC_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES","3"))
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")

app = FastAPI(title=f"AdvBot-{BOT_ID}")
init_db()

if MODE == 'paper':
    ex = PaperExchange(symbol=PAIR, base_currency="USDT", base_capital=BASE_CAPITAL)
else:
    ex = RealExchange(exchange='binance', api_key=API_KEY, api_secret=API_SECRET, symbol=PAIR)

feed = DataFeed(exchange='binance', symbol=PAIR, timeframe=TIMEFRAME)
TRAIL_BASE = None  # precio base para trailing

def choose():
    df = feed.candles(limit=220)
    if STRATEGY == 'combo':
        return signal_combo(df)
    if STRATEGY == 'ema':
        return signal_ema(df)
    if STRATEGY == 'rsi_macd':
        return signal_rsi_macd(df)
    if STRATEGY == 'scalping':
        return signal_scalping(df)
    return None

async def loop():
    global TRAIL_BASE
    while True:
        try:
            sig = choose()
            now = datetime.utcnow()

            # Salidas (TP/SL/tiempo + trailing stop)
            if hasattr(ex, 'position') and ex.position:
                price_now = ex._price()
                entry = ex.position.entry_price
                change = (price_now - entry) / entry

                # trailing stop dinámico
                if change > 0:
                    if TRAIL_BASE is None or price_now > TRAIL_BASE:
                        TRAIL_BASE = price_now
                    if (TRAIL_BASE - price_now) / TRAIL_BASE >= TRAILING_PCT:
                        ok,_, qty, ep, xp = ex.sell()
                        pnl = (xp - ep) * qty
                        record_trade(BOT_ID, PAIR, 'sell', qty, ep, xp, pnl, ex.position.opened_at if ex.position else now, now, STRATEGY)
                        update_bot_stats(BOT_ID, won=(pnl>0))
                        TRAIL_BASE = None
                        await asyncio.sleep(LOOP_SECONDS)
                        continue

                if change <= -STOP_LOSS_PCT or change >= TAKE_PROFIT_PCT or (now - ex.position.opened_at).total_seconds() > MAX_OPEN_TIME_SEC:
                    ok,_, qty, ep, xp = ex.sell()
                    pnl = (xp - ep) * qty
                    record_trade(BOT_ID, PAIR, 'sell', qty, ep, xp, pnl, ex.position.opened_at if ex.position else now, now, STRATEGY)
                    update_bot_stats(BOT_ID, won=(pnl>0))
                    TRAIL_BASE = None

            # Entradas
            if sig == 'buy' and (not hasattr(ex,'position') or ex.position is None):
                if MODE == 'paper':
                    ok,_, qty, price = ex.buy(size_pct=SIZE_PCT)
                    if ok:
                        record_trade(BOT_ID, PAIR, 'buy', qty, price, price, 0.0, now, now, STRATEGY)
                else:
                    pass

            # Adaptativo (reduce riesgo tras pérdidas consecutivas)
            stats = fetch_bot_stats(BOT_ID)
            if ADAPTIVE and stats.get('consecutive_losses',0) >= MAX_CONSEC_LOSSES:
                globals()['SIZE_PCT'] = max(0.05, SIZE_PCT*0.8)
                globals()['TAKE_PROFIT_PCT'] = max(0.006, TAKE_PROFIT_PCT*0.9)
                globals()['STOP_LOSS_PCT'] = min(0.012, STOP_LOSS_PCT*1.1)

            await asyncio.sleep(LOOP_SECONDS)
        except Exception as e:
            await asyncio.sleep(LOOP_SECONDS)

@app.get('/status')
def status():
    eq = ex.equity() if hasattr(ex,'equity') else None
    return {"bot_id": BOT_ID, "pair": PAIR, "strategy": STRATEGY, "mode": MODE, "equity": eq}

if __name__ == '__main__':
    import uvicorn, sys
    if '--worker' in sys.argv:
        asyncio.run(loop())
    else:
        uvicorn.run(app, host='0.0.0.0', port=8000)
"""

STRATEGIES_PY = """\
import ccxt, pandas as pd, pandas_ta as ta

class DataFeed:
    def __init__(self, exchange: str, symbol: str, timeframe: str):
        ex_cls = getattr(ccxt, exchange)
        self.ex = ex_cls({'enableRateLimit': True})
        self.symbol = symbol
        self.timeframe = timeframe
    def candles(self, limit=220) -> pd.DataFrame:
        ohlcv = self.ex.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        return df

def signal_ema(df: pd.DataFrame, fast=9, slow=21):
    df = df.copy()
    df['ema_f'] = ta.ema(df['close'], length=fast)
    df['ema_s'] = ta.ema(df['close'], length=slow)
    if len(df) < slow + 2: return None
    if df['ema_f'].iloc[-2] < df['ema_s'].iloc[-2] and df['ema_f'].iloc[-1] > df['ema_s'].iloc[-1]:
        return 'buy'
    if df['ema_f'].iloc[-2] > df['ema_s'].iloc[-2] and df['ema_f'].iloc[-1] < df['ema_s'].iloc[-1]:
        return 'sell'
    return None

def signal_rsi_macd(df: pd.DataFrame, rsi_low=30, rsi_high=70):
    df = df.copy()
    df['rsi'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df['macd'] = macd['MACD_12_26_9']; df['macds'] = macd['MACDs_12_26_9']
    if len(df) < 40: return None
    buy  = (df['rsi'].iloc[-2] < rsi_low and df['rsi'].iloc[-1] > rsi_low) and (df['macd'].iloc[-2] < df['macds'].iloc[-2] and df['macd'].iloc[-1] > df['macds'].iloc[-1])
    sell = (df['rsi'].iloc[-2] > rsi_high and df['rsi'].iloc[-1] < rsi_high) and (df['macd'].iloc[-2] > df['macds'].iloc[-2] and df['macd'].iloc[-1] < df['macds'].iloc[-1])
    if buy: return 'buy'
    if sell: return 'sell'
    return None

def signal_scalping(df: pd.DataFrame):
    df = df.copy()
    c1 = df.iloc[-1]
    body = abs(c1['close'] - c1['open']); rng = c1['high'] - c1['low']
    if rng == 0: return None
    if (body / rng) > 0.7 and c1['close'] > c1['open']:
        return 'buy'
    return None

def signal_combo(df: pd.DataFrame):
    # Señal combinada: requiere acuerdo EMA + RSI/MACD (más estricta)
    s1 = signal_ema(df); s2 = signal_rsi_macd(df)
    if s1 == 'buy' and s2 == 'buy': return 'buy'
    if s1 == 'sell' or s2 == 'sell': return 'sell'
    return None
"""

EXCHANGE_PY = """\
import ccxt
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Position:
    qty: float
    entry_price: float
    opened_at: datetime

class PaperExchange:
    def __init__(self, symbol: str, base_currency: str='USDT', base_capital: float=1000):
        self.symbol = symbol
        self.cash = base_capital
        self.position: Optional[Position] = None
        self.fee = 0.0006
        self.ex = ccxt.binance({'enableRateLimit': True})
    def _price(self) -> float:
        return float(self.ex.fetch_ticker(self.symbol)['last'])
    def buy(self, size_pct: float=0.1):
        price = self._price()
        notional = self.cash * size_pct
        if notional <= 0: return False, 'NOCASH', 0.0, price
        qty = (notional / price) * (1 - self.fee)
        self.cash -= notional
        self.position = Position(qty=qty, entry_price=price, opened_at=datetime.utcnow())
        return True, 'FILLED', qty, price
    def sell(self):
        if not self.position: return False, 'NOPOS', 0.0, 0.0, 0.0
        price = self._price()
        gross = self.position.qty * price * (1 - self.fee)
        pnl = gross - (self.position.qty * self.position.entry_price)
        qty = self.position.qty; entry = self.position.entry_price
        self.cash += gross; self.position = None
        return True, 'FILLED', qty, entry, price
    def equity(self):
        if not self.position: return self.cash
        return self.cash + self.position.qty * self._price()

class RealExchange:
    def __init__(self, exchange: str, api_key: str, api_secret: str, symbol: str):
        ex_cls = getattr(ccxt, exchange)
        self.ex = ex_cls({'enableRateLimit': True, 'apiKey': api_key, 'secret': api_secret, 'options': {'defaultType':'spot'}})
        self.symbol = symbol
    def _price(self) -> float:
        return float(self.ex.fetch_ticker(self.symbol)['last'])
"""

STORAGE_PY = """\
from sqlalchemy import create_engine, text
from datetime import datetime

ENGINE = None
def _engine():
    global ENGINE
    if ENGINE is None:
        ENGINE = create_engine("sqlite:///trades.db", future=True)
    return ENGINE

def init_db():
    with _engine().begin() as con:
        con.execute(text(\"\"\"CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT, pair TEXT, side TEXT, qty REAL,
            entry_price REAL, exit_price REAL, pnl REAL,
            opened_at TEXT, closed_at TEXT, strategy TEXT
        )\"\"\"))
        con.execute(text(\"\"\"CREATE TABLE IF NOT EXISTS bot_stats(
            bot_id TEXT PRIMARY KEY, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
            consecutive_losses INTEGER DEFAULT 0, last_update TEXT
        )\"\"\"))

def record_trade(bot_id, pair, side, qty, entry, exitp, pnl, opened_at, closed_at, strategy):
    with _engine().begin() as con:
        con.execute(text(\"\"\"INSERT INTO trades(bot_id,pair,side,qty,entry_price,exit_price,pnl,opened_at,closed_at,strategy)
        VALUES(:b,:p,:s,:q,:e1,:e2,:pl,:o,:c,:st)\"\"\"), {
            'b': bot_id,'p': pair,'s': side,'q': qty,'e1': entry,'e2': exitp,'pl': pnl,
            'o': (opened_at.isoformat() if hasattr(opened_at,'isoformat') else str(opened_at)),
            'c': (closed_at.isoformat() if hasattr(closed_at,'isoformat') else str(closed_at)),
            'st': strategy
        })

def fetch_bot_stats(bot_id:str):
    with _engine().begin() as con:
        row = con.execute(text(\"SELECT wins,losses,consecutive_losses FROM bot_stats WHERE bot_id=:b\"), {'b':bot_id}).fetchone()
        if not row:
            con.execute(text(\"INSERT INTO bot_stats(bot_id,wins,losses,consecutive_losses,last_update) VALUES(:b,0,0,0,:t)\"), {'b':bot_id,'t':datetime.utcnow().isoformat()})
            return {'wins':0,'losses':0,'consecutive_losses':0}
        return {'wins':row[0],'losses':row[1],'consecutive_losses':row[2]}

def update_bot_stats(bot_id:str, won:bool):
    with _engine().begin() as con:
        row = con.execute(text(\"SELECT wins,losses,consecutive_losses FROM bot_stats WHERE bot_id=:b\"), {'b':bot_id}).fetchone()
        if not row:
            wins = 1 if won else 0; losses = 0 if won else 1; cl = 0 if won else 1
            con.execute(text(\"INSERT INTO bot_stats(bot_id,wins,losses,consecutive_losses,last_update) VALUES(:b,:w,:l,:c,:t)\"), {'b':bot_id,'w':wins,'l':losses,'c':cl,'t':datetime.utcnow().isoformat()})
        else:
            wins = row[0] + (1 if won else 0)
            losses = row[1] + (0 if won else 1)
            cl = 0 if won else row[2] + 1
            con.execute(text(\"UPDATE bot_stats SET wins=:w, losses=:l, consecutive_losses=:c, last_update=:t WHERE bot_id=:b\"), {'w':wins,'l':losses,'c':cl,'t':datetime.utcnow().isoformat(),'b':bot_id})
"""

RENDER_YAML = """\
services:
  - type: web
    name: {service_name}
    env: docker
    plan: starter    # ajustá tu plan en Render
    autoDeploy: true
    region: oregon   # ajustá región si querés
    branch: main
    healthCheckPath: /status
"""

GHA_WORKFLOW = """\
name: ci
on:
  push:
    branches: [ "main" ]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m compileall .
"""

@dataclass
class BotCfg:
    name: str
    bot_id: str
    pair: str
    strategy: str
    timeframe: str

def run(cmd, cwd=None):
    print(">", cmd)
    subprocess.check_call(cmd, shell=True, cwd=cwd)

def scaffold(cfg: BotCfg) -> Path:
    root = Path("bots") / cfg.name
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text(REQS)
    (root / "Dockerfile").write_text(DOCKERFILE)
    (root / "main.py").write_text(MAIN_PY.format(
        bot_id=cfg.bot_id, pair=cfg.pair, strategy=cfg.strategy, timeframe=cfg.timeframe
    ))
    (root / "strategies.py").write_text(STRATEGIES_PY)
    (root / "exchange.py").write_text(EXCHANGE_PY)
    (root / "storage.py").write_text(STORAGE_PY)
    # .env por defecto (paper)
    (root / ".env").write_text(textwrap.dedent(f"""\
        MODE=paper
        BOT_ID={cfg.bot_id}
        PAIR={cfg.pair}
        STRATEGY={cfg.strategy}
        TIMEFRAME={cfg.timeframe}
        SIZE_PCT=0.12
        STOP_LOSS_PCT=0.006
        TAKE_PROFIT_PCT=0.012
        TRAILING_PCT=0.004
        LOOP_SECONDS=7
        BASE_CAPITAL=1000
    """))
    # Render blueprint + CI
    (root / "render.yaml").write_text(RENDER_YAML.format(service_name=cfg.name))
    gha = root / ".github" / "workflows"
    gha.mkdir(parents=True, exist_ok=True)
    (gha / "ci.yml").write_text(GHA_WORKFLOW)
    # README mínimo
    (root / "README.md").write_text(f"# {cfg.name}\\n\\nBot de trading avanzado (paper). Endpoint /status.\\n")
    return root

def github_create_repo(repo_name: str, private=True):
    if not GITHUB_TOKEN or not GITHUB_USERNAME:
        print("⚠️  GITHUB_TOKEN/GITHUB_USERNAME no definidos — me salto GitHub.")
        return None
    url = "https://api.github.com/user/repos"
    hdr = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept":"application/vnd.github+json"}
    data = {"name": repo_name, "private": private, "auto_init": False}
    r = requests.post(url, headers=hdr, json=data)
    if r.status_code not in (200,201):
        raise RuntimeError(f"GitHub create repo error: {r.status_code} {r.text}")
    return r.json()["html_url"], r.json()["ssh_url"]

def git_init_push(path: Path, repo_ssh_url: str):
    run("git init", cwd=path)
    run('git checkout -b main', cwd=path)
    run("git add .", cwd=path)
    run('git commit -m "init bot"', cwd=path)
    run(f"git remote add origin {repo_ssh_url}", cwd=path)
    run("git push -u origin main", cwd=path)

def render_create_service(repo_url_https: str, service_name: str):
    """
    Intenta crear servicio en Render apuntando al repo (Docker).
    Nota: requiere que tu cuenta de Render tenga permisos con GitHub.
    """
    if not RENDER_API_KEY or not RENDER_OWNER_ID:
        print("⚠️  RENDER_API_KEY/RENDER_OWNER_ID no definidos — me salto Render.")
        return None
    url = "https://api.render.com/v1/services"
    hdr = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept":"application/json", "Content-Type":"application/json"}
    payload = {
        "ownerId": RENDER_OWNER_ID,
        "name": service_name,
        "type": "web_service",
        "repo": repo_url_https,
        "branch": "main",
        "autoDeploy": True,
        "rootDir": ".",
        "envVars": [
            {"key":"PORT","value":"8000"},
            {"key":"MODE","value":"paper"}
        ],
        "region": "oregon",
        "serviceDetails": {
            "env": "docker",
            "plan": "starter",
            "healthCheckPath": "/status"
        }
    }
    r = requests.post(url, headers=hdr, json=payload)
    if r.status_code not in (200,201):
        raise RuntimeError(f"Render create service error: {r.status_code} {r.text}")
    return r.json()

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--bot_id", default="1")
    p.add_argument("--pair", default="BTC/USDT")
    p.add_argument("--strategy", default="combo")
    p.add_argument("--timeframe", default="1m")
    args = p.parse_args()

    cfg = BotCfg(name=args.name, bot_id=args.bot_id, pair=args.pair, strategy=args.strategy, timeframe=args.timeframe)
    path = scaffold(cfg)
    print(f"✅ Proyecto creado en {path}")

    if GITHUB_TOKEN and GITHUB_USERNAME:
        https_url, ssh_url = github_create_repo(cfg.name, private=True)
        print(f"🔗 Repo GitHub: {https_url}")
        # Necesitás tener una SSH key configurada en GitHub para push por SSH.
        try:
            git_init_push(path, ssh_url)
            print("🚀 Código subido a GitHub.")
        except Exception as e:
            print("⚠️ Error subiendo a GitHub (¿clave SSH configurada?):", e)
        # Intentar crear servicio en Render
        try:
            svc = render_create_service(https_url, cfg.name)
            if svc:
                print("🟢 Servicio Render creado:", svc.get("id","(sin id)"))
                print("   Revisa tu dashboard de Render para el deploy inicial.")
        except Exception as e:
            print("⚠️ Error creando servicio en Render:", e)
    else:
        print("ℹ️ Salté GitHub/Render por falta de tokens. El bot quedó listo localmente.")

if __name__ == "__main__":
    main()
