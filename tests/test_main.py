
from main import app



# Test 1: Root URL
def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Amura Healthcare Voice AI Agent is running"}

# Test 2: Invalid URL (404 Check)
def test_invalid_url(client):
    response = client.get("/invalid-path")
    assert response.status_code == 404


