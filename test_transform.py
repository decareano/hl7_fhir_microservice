import requests

hl7_message = """MSH|^~\&|LAB|HOSPITAL|EPIC|HOSPITAL|202608230900||ORU^R01|101|P|2.3\r
PID|1||45678^^^MRN||DOE^JOHN||19800101|M\r
OBX|1|NM|GLU^Glucose||140|mg/dL|70-110|H\r"""

payload = {"hl7_message": hl7_message}
response = requests.post("http://localhost:5005/transform", json=payload)
print(response.json())
