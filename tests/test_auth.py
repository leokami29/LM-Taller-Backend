def test_login_success(client, seed_company_and_admin):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "password123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "admin@test.com"


def test_login_invalid_password(client, seed_company_and_admin):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrong"},
    )
    assert res.status_code == 401


def test_me_requires_token(client, seed_company_and_admin):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
