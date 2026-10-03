import pytest
from rest_framework.test import APIClient

from .factories import make_user


@pytest.fixture
def user(db):
    return make_user("alice")


@pytest.fixture
def other_user(db):
    return make_user("bob")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def other_api(other_user):
    client = APIClient()
    client.force_authenticate(other_user)
    return client


@pytest.fixture
def web(client, user):
    client.force_login(user)
    return client
