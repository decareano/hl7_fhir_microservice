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

    # MSH segment
    msh_segment = parsed_message[0]
    sending_app = msh_segment[2]
    receiving_app = msh_segment[4]

    # PID segment
    pid_segment = parsed_message[1]
    patient_name = pid_segment[4]
    patient_mrn = pid_segment[3]

    # OBX segment
    obx_segment = parsed_message[2]
    test_name = obx_segment[3]
    test_value = str(obx_segment[5])
    units = obx_segment[6]
    ref_range = obx_segment[7]
    abnormal_flag = obx_segment[8]

    # --- Original custom JSON response ---
    custom_response = {
        "status": "success",
        "sending_app": sending_app,
        "patient_name": patient_name,
        "test_name": test_name,
        "test_value": test_value,
        "abnormal_flag": abnormal_flag,
    }

    # --- FHIR Observation ---
    fhir_observation = {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "15074-8", "display": "glucose"}
            ]
        },
        "valueQuantity": {
            "value": float(test_value),
            "unit": units,
            "system": "http://unitsofmeasure.org",
        },
    }

    # --- Return both ---
    return jsonify({"original": custom_response, "fhir": fhir_observation})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
