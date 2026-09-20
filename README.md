## Key Components in app.py

- flatten() — cleans nested lists from the hl7 library into strings
- LOINC_MAP — maps HL7 test codes → LOINC codes and display names
- post_route() — main transformation logic

## Deployment

- Hosted on Render (manual ZIP upload, no GitHub)
- Start command: gunicorn app:app
- Uses PORT environment variable

---

## ✅ Completed

- Flask app with /ping and /transform
- HL7 parsing with hl7 library
- Extract MSH, PID, OBX fields
- flatten() for clean string extraction
- Loop over multiple OBX segments
- Build one FHIR Observation per OBX
- LOINC mapping via LOINC_MAP
- Deployed to Render
