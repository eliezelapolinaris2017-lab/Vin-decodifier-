#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# python-OBD
import obd

app = FastAPI(title="Launch-like OBD Web")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- Estado de conexión global ----------
class OBDState:
    def __init__(self):
        self.connection: Optional[obd.OBD] = None
        self.port: Optional[str] = None
        self.protocol: Optional[str] = None

state = OBDState()

# ---------- Utilidades ----------
SUPPORTED_PIDS = {
    # PID : objeto comando de python-OBD
    "RPM": obd.commands.RPM,
    "SPEED": obd.commands.SPEED,
    "COOLANT_TEMP": obd.commands.COOLANT_TEMP,
    "INTAKE_TEMP": obd.commands.INTAKE_TEMP,
    "FUEL_LEVEL": obd.commands.FUEL_LEVEL,
    "MAF": obd.commands.MAF,
    "THROTTLE_POS": obd.commands.THROTTLE_POS,
    "RUN_TIME": obd.commands.RUN_TIME,
    "O2_B1S1": obd.commands.O2_B1S1,
    "SHORT_FUEL_TRIM_1": obd.commands.SHORT_FUEL_TRIM_1,
    "LONG_FUEL_TRIM_1": obd.commands.LONG_FUEL_TRIM_1,
    "ELM_VOLTAGE": obd.commands.ELM_VOLTAGE,  # voltaje reportado por ELM
    "STATUS": obd.commands.STATUS,            # monitores / MIL
}

def ensure_connected() -> bool:
    return state.connection is not None and state.connection.status() == obd.OBDStatus.CAR_CONNECTED

def result_to_primitive(r: obd.OBDResponse) -> Any:
    if r is None or r.value is None:
        return None
    try:
        # value.magnitude si es Quantity, o str
        return getattr(r.value, "magnitude", str(r.value))
    except Exception:
        return str(r.value)

# ---------- Modelos ----------
class ConnectPayload(BaseModel):
    port: Optional[str] = None   # Si None, auto
    fast: bool = True            # intenta rápida (fast)
    baudrate: Optional[int] = None

class LiveQuery(BaseModel):
    pids: List[str] = ["RPM", "SPEED", "COOLANT_TEMP"]
    interval_ms: int = 500

# ---------- Rutas API ----------
@app.get("/", response_class=HTMLResponse)
def root():
    with open(os.path.join("static", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/ports")
def list_ports():
    ports = obd.scan_serial()  # lista puertos disponibles
    return {"ok": True, "ports": ports}

@app.post("/api/connect")
def connect(payload: ConnectPayload):
    if state.connection is not None:
        try:
            state.connection.close()
        except Exception:
            pass
        state.connection = None

    kwargs = {}
    if payload.port:
        kwargs["portstr"] = payload.port
    if payload.fast:
        kwargs["fast"] = True
    if payload.baudrate:
        kwargs["baudrate"] = payload.baudrate

    # Conexión (bloqueante, pero rápida)
    conn = obd.OBD(**kwargs)  # autodetecta protocolo
    if conn.status() in (obd.OBDStatus.NOT_CONNECTED, obd.OBDStatus.ELM_CONNECTED):
        return JSONResponse({"ok": False, "status": str(conn.status())}, status_code=400)

    state.connection = conn
    state.port = conn.port_name()
    state.protocol = str(conn.protocol_name()) if conn.protocol_name() else None

    return {"ok": True, "status": str(conn.status()), "port": state.port, "protocol": state.protocol}

@app.post("/api/disconnect")
def disconnect():
    if state.connection:
        try:
            state.connection.close()
        except Exception:
            pass
    state.connection = None
    state.port = None
    state.protocol = None
    return {"ok": True}

@app.get("/api/status")
def status():
    st = str(state.connection.status()) if state.connection else "DISCONNECTED"
    return {"ok": True, "connected": ensure_connected(), "status": st, "port": state.port, "protocol": state.protocol}

@app.get("/api/vin")
def read_vin():
    if not ensure_connected():
        return JSONResponse({"ok": False, "error": "No conectado"}, status_code=400)
    r = state.connection.query(obd.commands.GET_VIN)  # modo 09 02
    vin = str(r.value) if r.value else None
    return {"ok": True, "vin": vin}

@app.get("/api/dtc")
def read_dtc():
    if not ensure_connected():
        return JSONResponse({"ok": False, "error": "No conectado"}, status_code=400)
    r = state.connection.query(obd.commands.GET_DTC)  # modo 03
    codes = r.value if r and r.value else []
    # codes es lista de tuplas [(code, desc), ...] si el adapter provee desc
    parsed = []
    for item in codes:
        if isinstance(item, tuple) and len(item) >= 1:
            code = item[0]
            desc = item[1] if len(item) > 1 else ""
            parsed.append({"code": code, "desc": desc})
        else:
            parsed.append({"code": str(item), "desc": ""})
    return {"ok": True, "dtc": parsed}

@app.delete("/api/dtc")
def clear_dtc():
    if not ensure_connected():
        return JSONResponse({"ok": False, "error": "No conectado"}, status_code=400)
    r = state.connection.query(obd.commands.CLEAR_DTC)  # modo 04
    return {"ok": True, "cleared": True, "raw": str(r.value) if r else None}

@app.get("/api/pids")
def list_pids():
    return {"ok": True, "pids": list(SUPPORTED_PIDS.keys())}

@app.get("/api/live")
def live_snapshot(names: str = Query(default="RPM,SPEED,COOLANT_TEMP")):
    if not ensure_connected():
        return JSONResponse({"ok": False, "error": "No conectado"}, status_code=400)
    wanted = [n.strip().upper() for n in names.split(",") if n.strip()]
    out: Dict[str, Any] = {}
    for n in wanted:
        cmd = SUPPORTED_PIDS.get(n)
        if not cmd:
            out[n] = None
            continue
        resp = state.connection.query(cmd)
        out[n] = result_to_primitive(resp)
    return {"ok": True, "data": out}

@app.get("/api/monitors")
def monitors():
    if not ensure_connected():
        return JSONResponse({"ok": False, "error": "No conectado"}, status_code=400)
    resp = state.connection.query(obd.commands.STATUS)  # MIL y monitores
    # STATUS devuelve un objeto con flags; lo convertimos a dict legible
    data = str(resp.value) if resp and resp.value else ""
    return {"ok": True, "status_text": data}

# ---------- WebSocket para streaming de datos ----------
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    if not ensure_connected():
        await ws.send_text(json.dumps({"type": "error", "msg": "No conectado"}))
        await ws.close()
        return

    # Primer mensaje del cliente debe indicar pids y frecuencia
    try:
        init = await ws.receive_text()
        cfg = json.loads(init)
        pid_names = [p.upper() for p in cfg.get("pids", ["RPM", "SPEED"])]
        interval_ms = int(cfg.get("interval_ms", 500))
    except Exception:
        pid_names = ["RPM", "SPEED"]
        interval_ms = 500

    try:
        while True:
            if not ensure_connected():
                await ws.send_text(json.dumps({"type": "error", "msg": "Conexión perdida"}))
                await ws.close()
                break
            payload = {}
            for n in pid_names:
                cmd = SUPPORTED_PIDS.get(n)
                if not cmd:
                    payload[n] = None
                    continue
                r = state.connection.query(cmd)
                payload[n] = result_to_primitive(r)
            await ws.send_text(json.dumps({"type": "live", "data": payload}))
            await asyncio.sleep(max(0.1, interval_ms / 1000))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "msg": str(e)}))
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
