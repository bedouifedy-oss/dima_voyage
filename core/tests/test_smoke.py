import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_admin_login_page_loads(client):
    """Basic smoke test to ensure the admin interface is reachable."""
    url = reverse("admin:login")
    response = client.get(url)
    assert response.status_code == 200
