import requests

hl7_message = """MSH|^~\&|LAB|HOSPITAL|EPIC|HOSPITAL|202608230900||ORU^R01|101|P|2.3\r
PID|1||45678^^^MRN||DOE^JOHN||19800101|M\r
OBR|1|845439^GHH|57357^LAB|CBC^Complete Blood Count|||202608230800\r
OBX|1|NM|WBC^White Blood Cell||7.2|k/uL|4.0-10.5|N\r
OBX|2|NM|RBC^Red Blood Cell||4.8|m/uL|4.2-5.4|N\r
OBX|3|NM|HGB^Hemoglobin||14.5|g/dL|12.0-16.0|N\r
OBX|4|NM|HCT^Hematocrit||42.0|%|36-46|N\r
OBX|5|NM|PLT^Platelet||250|k/uL|150-400|N\r
NTE|1||Specimen slightly hemolyzed\r"""

payload = {"hl7_message": hl7_message}
response = requests.post("http://localhost:5005/transform", json=payload)
print(response.json())
