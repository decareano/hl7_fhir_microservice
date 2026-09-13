from flask import Flask, request, jsonify
import hl7
import json
import jsonschema
import os

app = Flask(__name__)


@app.route("/ping", methods=["GET"])
def ping_route():
    return jsonify({"status": "healthy", "message": "ok"}), 200


@app.route("/transform", methods=["POST"])
def post_route():
    data = request.get_json()
    hl7_string = data["hl7_message"]
    parsed_message = hl7.parse(hl7_string)
    len(parsed_message)
    [seg[0] for seg in parsed_message]

    # MSH segment
    msh_segment = parsed_message[0]
    sending_app = msh_segment[2]
    receiving_app = msh_segment[4]

    # PID segment
    pid_segment = parsed_message[1]
    patient_name = pid_segment[4]
    patient_mrn = pid_segment[3]
    patient_dob = pid_segment[7]

    # Find all OBX segments
    obx_segments = []
    for item in parsed_message:
        if item[0] == "OBX":
            obx_segments.append(item)

    # Build a FHIR Observation for each OBX
    fhir_observations = []
    for field in obx_segments:
        test_name = field[3]
        test_value = str(field[5])
        units = field[6]
        ref_range = field[7]
        abnormal_flag = field[8]

        fhir_observation = {
            "resourceType": "Observation",
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "15074-8",
                        "display": "glucose",
                    }
                ]
            },
            "valueQuantity": {
                "value": float(test_value),
                "unit": units,
                "system": "http://unitsofmeasure.org",
            },
        }
        fhir_observations.append(fhir_observation)

    return jsonify(
        {"fhir_observations": fhir_observations, "count": len(fhir_observations)}
    )
