from flask import Flask, request, jsonify
import hl7
import json
import jsonschema
import os

app = Flask(__name__)
# need to add a comment


def flatten(value):
    if isinstance(value, str):
        return value
    elif isinstance(value, list):
        empList = []
        for item in value:
            myVar = flatten(item)
            empList.append(myVar)
        return "^".join(empList)


LOINC_MAP = {
    "WBC": {"code": "6690-2", "display": "Leukocytes"},
    "RBC": {"code": "789-8", "display": "Erythrocytes"},
    "HGB": {"code": "718-7", "display": "hemoglobin"},
    "HCT": {"code": "4544-3", "display": "hematocrit"},
    "PLT": {"code": "777-3", "display": "platelets"},
    "GLU": {"code": "15074-8", "display": "glucose"},
}


@app.route("/ping", methods=["GET"])
def ping_route():
    return jsonify({"status": "healthy", "message": "ok"}), 200


@app.route("/transform", methods=["POST"])
def post_route():
    data = request.get_json()
    hl7_string = data["hl7_message"]
    parsed_message = hl7.parse(hl7_string)

    # MSH segment
    msh_segment = parsed_message[0]
    sending_app = flatten(msh_segment[2])
    receiving_app = flatten(msh_segment[4])

    # PID segment
    pid_segment = parsed_message[1]
    patient_name = flatten(pid_segment[4])
    patient_mrn = flatten(pid_segment[3])
    patient_dob = flatten(pid_segment[7])

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
        units = flatten(field[6])
        ref_range = flatten(field[7])
        abnormal_flag = flatten(field[8])

        test_code = test_name.split("^")[0]
        loinc_entry = LOINC_MAP.get(
            test_code, {"code": "unknown", "display": test_code}
        )

        flag_display = {
            "H": "High",
            "L": "Low",
            "N": "Normal",
        }
        flag_text = flag_display.get(abnormal_flag, abnormal_flag)

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
            "valueQuantity": {
                "value": float(test_value),
                "unit": units,
                "system": "http://unitsofmeasure.org",
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
        fhir_observations.append(fhir_observation)

    return jsonify(
        {"fhir_observations": fhir_observations, "count": len(fhir_observations)}
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
