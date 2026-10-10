from flask import Flask, request, jsonify
import hl7
import os

app = Flask(__name__)


def flatten(value):
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
    if len(hl7_string) > 10000:
        return jsonify({"error": "message too long"}), 400
    parsed_message = hl7.parse(hl7_string)

    # MSH segment
    msh_segment = parsed_message[0]
    sending_app = flatten(msh_segment[2])
    receiving_app = flatten(msh_segment[4])

    # PID segment
    pid_segment = parsed_message[1]
    patient_name = flatten(pid_segment[5])
    name_parts = patient_name.split("^")
    family = name_parts[0]
    if len(name_parts) >= 2:
        given = name_parts[1]
    else:
        given = ""
    patient_mrn = flatten(pid_segment[3])
    patient_mrn = patient_mrn.split("^")[0]
    patient_dob = flatten(pid_segment[7])
    if len(patient_dob) == 8:
        dob_iso = patient_dob[:4] + "-" + patient_dob[4:6] + "-" + patient_dob[6:8]
    else:
        dob_iso = None

    # Find all OBX segments
    obx_segments = []
    for item in parsed_message:
        if str(item[0]) == "OBX":
            obx_segments.append(item)

    # Build a FHIR Observation for each OBX
    fhir_observations = []
    for field in obx_segments:
        test_name = flatten(field[3])
        test_value = flatten(field[5])
        try:
            value_num = float(test_value)
        except ValueError:
            value_num = None
        units = flatten(field[6])
        ref_range = flatten(field[7])
        abnormal_flag = flatten(field[8])

        test_code = test_name.split("^")[0]
        loinc_entry = LOINC_MAP.get(
            test_code, {"code": "unknown", "display": test_code}
        )

        flag_text = FLAG_DISPLAY.get(abnormal_flag, abnormal_flag)
        ref_parsed = parse_reference_range(ref_range)

        fhir_observation = {
            "resourceType": "Observation",
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": loinc_entry["code"],
                        "display": loinc_entry["display"],
                    }
                ]
            },
            "interpretation": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": abnormal_flag,
                            "display": flag_text,
                        }
                    ]
                }
            ],
        }
        if value_num is not None:
            fhir_observation["valueQuantity"] = {
                "value": value_num,
                "unit": units,
                "system": "http://unitsofmeasure.org",
            }
        else:
            fhir_observation["valueString"] = test_value

        if ref_parsed:
            fhir_observation["referenceRange"] = [ref_parsed]
        fhir_observations.append(fhir_observation)

    patient = {
        "resourceType": "Patient",
        "identifier": [{"value": patient_mrn}],
        "name": [{"family": family, "given": [given]}],
    }

    if dob_iso:
        patient["birthDate"] = dob_iso

    entries = []

    entries.append({"resource": patient})
    for obs in fhir_observations:
        entries.append({"resource": obs})
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}

    return jsonify(bundle, sort_keys=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
