from unittest.mock import patch, MagicMock
import requests
import pytest

from src.s3_backup.telegram import send_telegram_message


def test_send_telegram_message_success():
    """Test successful Telegram message send."""
    with patch("src.s3_backup.telegram.os.getenv") as mock_getenv:
        with patch("src.s3_backup.telegram.requests.post") as mock_post:
            mock_getenv.side_effect = lambda key: {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat-id",
            }.get(key)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            result = send_telegram_message("Test message")

            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "api.telegram.org" in call_args[0][0]
            assert call_args[1]["json"]["text"] == "Test message"
            assert call_args[1]["json"]["chat_id"] == "test-chat-id"


def test_send_telegram_message_missing_credentials():
    """Test Telegram send when credentials are missing."""
    with patch("src.s3_backup.telegram.os.getenv") as mock_getenv:
        mock_getenv.return_value = None

        result = send_telegram_message("Test message")

        assert result is False


def test_send_telegram_message_api_error():
    """Test Telegram send with API error response."""
    with patch("src.s3_backup.telegram.os.getenv") as mock_getenv:
        with patch("src.s3_backup.telegram.requests.post") as mock_post:
            mock_getenv.side_effect = lambda key: {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat-id",
            }.get(key)

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_post.return_value = mock_response

            result = send_telegram_message("Test message")

            assert result is False


def test_send_telegram_message_request_exception():
    """Test Telegram send with request exception."""
    with patch("src.s3_backup.telegram.os.getenv") as mock_getenv:
        with patch("src.s3_backup.telegram.requests.post") as mock_post:
            mock_getenv.side_effect = lambda key: {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat-id",
            }.get(key)

            mock_post.side_effect = requests.RequestException("Connection timeout")

            result = send_telegram_message("Test message")

            assert result is False


def test_send_telegram_message_calls_with_timeout():
    """Test that Telegram message send includes timeout."""
    with patch("src.s3_backup.telegram.os.getenv") as mock_getenv:
        with patch("src.s3_backup.telegram.requests.post") as mock_post:
            mock_getenv.side_effect = lambda key: {
                "TELEGRAM_BOT_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "test-chat-id",
            }.get(key)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            send_telegram_message("Test message")

            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["timeout"] == 10
