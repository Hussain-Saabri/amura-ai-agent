
def test_check_medicine_missing_param(client):
    response = client.get("/api/check-medicine")
    assert response.status_code == 200



def test_check_medicine_with_param(client):
    response = client.get("/api/check-medicine", params={"medicine_name": "soframycin"})
    assert response.status_code == 200

def test_check_medicine_with_url_param(client):
    response = client.get("/api/check-medicine?medicine_name=soframycin")
    assert response.status_code == 200