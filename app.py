from flask import Flask, request, jsonify
import hl7
import os

app = Flask(__name__)
app.json.sort_keys = False


def flatten(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    elif isinstance(value, list):
        empList = []
        for item in value:
            myVar = flatten(item)
            empList.append(myVar)
        return "^".join(empList)


def parse_reference_range(raw):
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("<"):
        try:
            val = float(raw[1:])
            return {"high": val, "text": raw}
        except ValueError:
            return {"text": raw}
    if raw.startswith(">"):
        try:
            val = float(raw[1:])
            return {"low": val, "text": raw}
        except ValueError:
            return {"text": raw}
    if "-" in raw:
        left, _, right = raw.partition("-")
        try:
            val_L = float(left)
            val_R = float(right)
            return {"low": val_L, "high": val_R, "text": raw}
        except ValueError:
            return {"text": raw}
    return {"text": raw}


def get_field(segment, index):
    if len(segment) > index:
        return flatten(segment[index])
    return ""


LOINC_MAP = {
    "WBC": {"code": "6690-2", "display": "Leukocytes"},
    "RBC": {"code": "789-8", "display": "Erythrocytes"},
    "HGB": {"code": "718-7", "display": "Hemoglobin"},
    "HCT": {"code": "4544-3", "display": "Hematocrit"},
    "PLT": {"code": "777-3", "display": "Platelets"},
    "GLU": {"code": "15074-8", "display": "Glucose"},
}

FLAG_DISPLAY = {
    "H": "High",
    "L": "Low",
    "N": "Normal",
}


@app.route("/ping", methods=["GET"])
def ping_route():
    return jsonify({"status": "healthy", "message": "ok"}), 200


@app.route("/transform", methods=["POST"])
def post_route():
    data = request.get_json()
    if not data or "hl7_message" not in data:
        return jsonify({"error": "missing hl7_message"}), 400
    hl7_string = data["hl7_message"]
    if not isinstance(hl7_string, str):
        return jsonify({"error": "needs to be a string"}), 400
    if len(hl7_string) > 5000:
        return jsonify({"error": "message too long"}), 400
    try:
        parsed_message = hl7.parse(hl7_string)
        pid_segments = []
        obx_segments = []
        for item in parsed_message:
            if str(item[0]) == "PID":
                pid_segments.append(item)
            if str(item[0]) == "OBX":
                obx_segments.append(item)
            if str(item[0]) == "OBR":
                obr_segment = item
        if not pid_segments:
            raise ValueError("missing PID segment")
        else:
            pid_segment = pid_segments[0]

        if obr_segment:
            obr_panel_name = get_field(obr_segment, 4)
            obr_datetime = get_field(obr_segment, 7)
        else:
            obr_panel_name = "Unknown panel"
            obr_datetime = ""

        # MSH segment
        msh_segment = parsed_message[0]
        sending_app = get_field(msh_segment, 2)
        receiving_app = get_field(msh_segment, 4)

        # PID segment

        patient_name = get_field(pid_segment, 5)
        name_parts = patient_name.split("^")
        family = name_parts[0]
        if len(name_parts) >= 2:
            given = name_parts[1]
        else:
            given = ""
        patient_mrn = get_field(pid_segment, 3)
        patient_mrn = patient_mrn.split("^")[0]
        patient_ref = "Patient/" + patient_mrn
        patient_dob = get_field(pid_segment, 7)
        if len(patient_dob) == 8:
            dob_iso = patient_dob[:4] + "-" + patient_dob[4:6] + "-" + patient_dob[6:8]
        else:
            dob_iso = None

        # Build a FHIR Observation for each OBX
        fhir_observations = []
        for field in obx_segments:
            test_name = get_field(field, 3)
            test_value = get_field(field, 5)
            try:
                value_num = float(test_value)
            except ValueError:
                value_num = None
            units = get_field(field, 6)
            ref_range = get_field(field, 7)
            abnormal_flag = get_field(field, 8)
            obs_datetime = get_field(field, 14)

            if len(obs_datetime) == 8:
                obs_datetime_iso = (
                    obs_datetime[:4] + "-" + obs_datetime[4:6] + "-" + obs_datetime[6:8]
                )
            elif len(obs_datetime) == 12:
                obs_datetime_iso = (
                    obs_datetime[:4]
                    + "-"
                    + obs_datetime[4:6]
                    + "-"
                    + obs_datetime[6:8]
                    + "T"
                    + obs_datetime[8:10]
                    + ":"
                    + obs_datetime[10:12]
                    + ":00"
                    + "Z"
                )
            elif len(obs_datetime) == 14:
                obs_datetime_iso = (
                    obs_datetime[:4]
                    + "-"
                    + obs_datetime[4:6]
                    + "-"
                    + obs_datetime[6:8]
                    + "T"
                    + obs_datetime[8:10]
                    + ":"
                    + obs_datetime[10:12]
                    + ":"
                    + obs_datetime[12:14]
                    + "Z"
                )
            else:
                obs_datetime_iso = None

            test_code = test_name.split("^")[0]
            obs_id = "obs-" + test_code
            loinc_entry = LOINC_MAP.get(
                test_code, {"code": "unknown", "display": test_code}
            )

            flag_text = FLAG_DISPLAY.get(abnormal_flag, abnormal_flag)
            ref_parsed = parse_reference_range(ref_range)

            fhir_observation = {
                "id": obs_id,
                "resourceType": "Observation",
                "status": "final",
                "subject": {"reference": patient_ref},
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "laboratory",
                                "display": "Laboratory",
                            }
                        ]
                    }
                ],
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": loinc_entry["code"],
                            "display": loinc_entry["display"],
                        }
                    ]
                },
            }
            if value_num is not None:
                fhir_observation["valueQuantity"] = {
                    "value": value_num,
                    "unit": units,
                    "system": "http://unitsofmeasure.org",
                }
            else:
                fhir_observation["valueString"] = test_value

            if abnormal_flag:
                fhir_observation["interpretation"] = [
                    {"coding": [{"code": abnormal_flag, "display": flag_text}]}
                ]

            if ref_parsed:
                fhir_observation["referenceRange"] = [ref_parsed]

            if obs_datetime_iso:
                fhir_observation["effectiveDateTime"] = obs_datetime_iso
            fhir_observations.append(fhir_observation)

        obs_references = []
        for ids in fhir_observations:
            my_id = ids["id"]
            obs_references.append({"reference": "Observation/" + my_id})

        patient = {
            "resourceType": "Patient",
            "identifier": [{"value": patient_mrn}],
            "name": [{"family": family, "given": [given]}],
            "id": patient_mrn,
        }

        if dob_iso:
            patient["birthDate"] = dob_iso

        diagnostic_report = {
            "id": "report-cbc",
            "resourceType": "DiagnosticReport",
            "status": "final",
            "subject": {"reference": patient_ref},
            "code": {"text": obr_panel_name},
            "result": obs_references,
        }

        entries = []

        entries.append({"resource": patient})
        for obs in fhir_observations:
            entries.append({"resource": obs})
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}

        return jsonify(bundle)
    except Exception as e:
        print(f"parse error: {e}")
        return jsonify({"error": "could not parse HL7 message"}), 422


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
