from backend.domain.enums import OrganizationType
from backend.schemas.admin import RegisterRequest


def test_register_request_accepts_employer():
    body = RegisterRequest(
        email="new.co@example.com",
        password="password123",
        organization_name="New Co",
        org_type=OrganizationType.EMPLOYER,
        profile_name="New Co Benefits",
    )
    assert body.org_type == OrganizationType.EMPLOYER
