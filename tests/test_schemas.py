"""
Tests for the shared and message schemas.
"""

from messaging.message_format import (
    create_social_media_message,
    create_web_scraping_message,
)
from messaging.schemas import MessageType, SourceType
from shared.models import Platform


def test_source_type_is_platform_alias():
    assert SourceType is Platform


def test_platform_members():
    expected = {
        "twitter",
        "facebook",
        "instagram",
        "linkedin",
        "telegram",
        "discord",
        "pastebin",
        "github",
        "manual",
        "system",
    }
    assert {member.value for member in Platform} == expected


def test_social_media_message_creation_and_routing_key():
    message = create_social_media_message(
        post_data={
            "post_id": "1",
            "author_id": "42",
            "author_username": "user",
            "content": "hello",
            "created_at": "2024-01-01T00:00:00",
        },
        source=SourceType.TWITTER,
        monitored_vip="Test VIP",
    )

    assert message.message_type == MessageType.SOCIAL_MEDIA
    assert message.routing_key == "social.twitter"
    assert message.data.content == "hello"


def test_web_scraping_message_routing_key():
    message = create_web_scraping_message(
        scraping_data={
            "url": "https://pastebin.com/abc",
            "content": "leaked credentials",
        },
        source=SourceType.PASTEBIN,
    )

    assert message.message_type == MessageType.WEB_SCRAPING
    assert message.routing_key == "scraping.pastebin"
