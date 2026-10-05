"""
Tests for message routing configuration.
"""

from messaging.message_format import create_social_media_message
from messaging.routing import message_router
from messaging.schemas import SourceType


def test_social_message_routes_to_threat_data_exchange():
    message = create_social_media_message(
        post_data={
            "post_id": "1",
            "author_id": "42",
            "author_username": "user",
            "content": "hello",
            "created_at": "2024-01-01T00:00:00",
        },
        source=SourceType.TWITTER,
    )

    info = message_router.get_routing_info(message)

    assert info["exchange"] == "threat_data"
    assert info["routing_key"] == "social.twitter"


def test_routing_config_is_valid():
    result = message_router.validate_routing_config()

    assert result["valid"] is True
    assert result["errors"] == []
