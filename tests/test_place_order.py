# Test 4: Testing the api order
def test_api_order(client):
    response = client.post("/api/order")
    assert response.status_code == 200

def test_api_order_empty_payload(client):
    payload = {}
    response = client.post("/api/order", json=payload)
    
    assert response.status_code == 200
   
    assert "Failed to save order" in response.json()["message"]
