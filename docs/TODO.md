# TODOs

- API: Decide how to handle path-style driver document creation. Either (a) remove the smoke-test path POST `/api/v1/driver-documents/{driver_id}` check, or (b) implement that endpoint so it creates a document for the given driver_id (current behavior is 405).
