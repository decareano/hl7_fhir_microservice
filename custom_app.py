from flask import Flask, request, jsonify
import hl7

app = Flask(__name__)


def get_field(segment, index):
    """Safely extracts field values from a parsed HL7 segment."""
    try:
        return str(segment[index][0])
    except (IndexError, TypeError):
        return ""


@app.route("/transform-custom", methods=["POST"])
def transform_custom():
    data = request.get_json()
    if not data or "hl7_message" not in data:
        return "missing hl7_message", 400

    parsed_message = hl7.parse(data["hl7_message"])
    pid_capture = parsed_message.segment("PID")

    id_fetch = get_field(pid_capture, 3)  # Patient ID
    name_fetch = get_field(pid_capture, 5)  # Patient Name (e.g. DOE^JOHN)
    gender_fetch = get_field(pid_capture, 8)  # Gender
    birth_fetch = get_field(pid_capture, 7)  # Date of Birth
    split_name = name_fetch.split("^")

    # Capture custom ZPV segment (ZPV|1|ICU|Bed 4)
    zpv_capture = parsed_message.segment("ZPV")
    zpv_loc = get_field(zpv_capture, 2)
    zpv_bed = get_field(zpv_capture, 3)

    # Capture custom ZAL segment for allergies
    zal_capture = parsed_message.segment("ZAL")
    zal_latex = get_field(zal_capture, 2)
    zal_swell = get_field(zal_capture, 3)
    zal_category = get_field(zal_capture, 4)

    fhir_mapping = {
        "resourceType": "Patient",
        "id": id_fetch,
        "name": [{"family": split_name[0], "given": [split_name[1]]}],
        "gender": gender_fetch,
        "birthDate": birth_fetch,
        "extension": [
            {
                "url": "http://example.com/fhir/StructureDefinition/patient-zpv-location",
                "valueString": f"{zpv_loc} - {zpv_bed}",
            },
            {
                "url": "http://example.com/fhir/StructureDefinition/patient-zal-allergy",
                "valueString": f"{zal_latex} - {zal_swell} - {zal_category}",
            },
        ],
    }

    return jsonify(fhir_mapping), 200


if __name__ == "__main__":
    app.run(debug=True)
