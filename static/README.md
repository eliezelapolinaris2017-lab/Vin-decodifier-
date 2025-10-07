# Launch-like OBD Web (Python)

Mini-scanner OBD-II en la web:
- Conectar a ELM327 (USB/BT/Serial)
- Leer VIN (modo 09), DTC (modo 03), Borrar DTC (modo 04)
- Monitores/estado (STATUS), Voltaje ELM
- Datos en vivo por WebSocket (RPM, SPEED, TEMP, etc.)

## Ejecutar local
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
