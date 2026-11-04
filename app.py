from flask import Flask, request, jsonify
import hl7
import os

app = Flask(__name__)
app.json.sort_keys = False


def flatten(a_value):
    if a_value is None:
        return ""
    elif isinstance(a_value, str):
        return a_value
    elif isinstance(a_value, list):
        result = []
        for item in a_value:
            flat_item = flatten(item)
            result.append(flat_item)
        return "^".join(result)


def get_field(segment, index):
    if len(segment) > index:
        return flatten(segment[index])
    return ""


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
    "PROT": {"code": "5804-0", "display": "Protein"},
    "RBC": {"code": "789-8", "display": "Erythrocytes"},
    "HGB": {"code": "718-7", "display": "Hemoglobin"},
    "HCT": {"code": "4544-3", "display": "Hematocrit"},
    "PLT": {"code": "777-3", "display": "Platelets"},
    "GLU": {"code": "5792-7", "display": "Glucose"},
    "K": {"code": "2823-3", "display": "Potassium"},
    "COLOR": {"code": "5778-6", "display": "Color"},
    "NIT": {"code": "5802-4", "display": "Nitrite"},
}

FLAG_DISPLAY = {
    "H": "High",
    "L": "Low",
    "N": "Normal",
    "A": "Abnormal",
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

    try:
        parsed_message = hl7.parse(hl7_string)
        pid_segments = []
        obx_segments = []
        obr_segment = None

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

        patient_name = get_field(pid_segment, 5)
        patient_mrn = get_field(pid_segment, 3)
        patient_dob = get_field(pid_segment, 7)

        named_parts = patient_name.split("^")
        family = named_parts[0]
        if len(named_parts) >= 2:
            given = named_parts[1]
        else:
            given = ""

        a_mrn = patient_mrn.split("^")[0]
        patient_ref = "Patient/" + a_mrn

        if len(patient_dob) == 8:
            dob_iso = patient_dob[:4] + "-" + patient_dob[4:6] + "-" + patient_dob[6:8]
        else:
            dob_iso = None

        if obr_segment:
            obr_panel_name = get_field(obr_segment, 4)
        else:
            obr_panel_name = "Unknown panel"

        fhir_observations = []
        validation_warnings = []

        for field in obx_segments:
            test_name = get_field(field, 3)
            test_value = get_field(field, 5)
            units = get_field(field, 6)
            ref_range = get_field(field, 7)
            abnormal_flag = get_field(field, 8)
            obs_datetime = get_field(field, 14)

            try:
                value_num = float(test_value)
            except ValueError:
                value_num = None

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

            if value_num is not None and units == "":
                warning_msg = "Missing units for test: " + test_name
                validation_warnings.append(warning_msg)

            fhir_observation = {
                "resourceType": "Observation",
                "id": obs_id,
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
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                "code": abnormal_flag,
                                "display": flag_text,
                            }
                        ]
                    }
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
            "identifier": [{"value": a_mrn}],
            "name": [{"family": family, "given": [given]}],
            "id": a_mrn,
        }

        if dob_iso:
            patient["birthDate"] = dob_iso

        diagnostic_report = {
            "id": "report-ua",
            "resourceType": "DiagnosticReport",
            "status": "final",
            "subject": {"reference": patient_ref},
            "code": {"text": obr_panel_name},
            "result": obs_references,
        }

        if len(validation_warnings) > 0:
            operation_outcome = {
                "resourceType": "OperationOutcome",
                "issue": [],
            }
            for msg in validation_warnings:
                operation_outcome["issue"].append(
                    {"severity": "warning", "code": "incomplete", "diagnostics": msg}
                )

        entries = []
        entries.append({"resource": patient})
        entries.append({"resource": diagnostic_report})

        if len(validation_warnings) > 0:
            entries.append({"resource": operation_outcome})

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
