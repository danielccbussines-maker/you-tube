import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import bot


def update(user=123, chat_type="private"):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user),
                           effective_chat=SimpleNamespace(type=chat_type),
                           effective_message=SimpleNamespace(reply_text=AsyncMock(), reply_audio=AsyncMock()))


class AccessTests(unittest.TestCase):
    def test_fail_closed_without_owner(self):
        self.assertEqual(bot.owner_ids(""), set())
        self.assertFalse(bot.allowed(update(), set()))

    def test_private_owner_only(self):
        self.assertTrue(bot.allowed(update(), {123}))
        self.assertFalse(bot.allowed(update(456), {123}))
        self.assertFalse(bot.allowed(update(chat_type="group"), {123}))

    def test_permissions_required_individually(self):
        item = dict(video_id="abcdefghijk", playlist_id=bot.PLAYLIST_ID,
                    rights_permission_ref="rights-record", youtube_permission_ref="platform-record")
        self.assertEqual(len(bot.approvals(json.dumps([item]))), 1)
        for field in ("rights_permission_ref", "youtube_permission_ref"):
            invalid = dict(item)
            del invalid[field]
            with self.assertRaises(ValueError):
                bot.approvals(json.dumps([invalid]))
        with self.assertRaises(ValueError):
            bot.approvals(json.dumps([item, item]))
        with self.assertRaises(ValueError):
            bot.approvals(json.dumps([dict(item, playlist_id="other")]))

    def test_url_injection_blocked(self):
        with patch("bot.subprocess.Popen") as process:
            with self.assertRaises(ValueError):
                bot.download("https://localhost/private", "/tmp")
            process.assert_not_called()


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_batch_sends_only_five_and_cleans_up(self):
        context = SimpleNamespace(bot_data={"owners": {123}, "approvals": [
            {"video_id": "abcdefghijk"} for _ in range(6)]}, args=[])
        paths = []
        def fake_download(video_id, directory):
            path = Path(directory) / "audio.mp3"
            path.write_bytes(b"mock-audio")
            paths.append(path)
            return path
        message = update()
        with patch("bot.download", side_effect=fake_download):
            await bot.taxi(message, context)
        self.assertEqual(message.effective_message.reply_audio.await_count, 5)
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertIn("/taxi 6", str(message.effective_message.reply_text.call_args_list))

    async def test_invalid_position_never_downloads(self):
        context = SimpleNamespace(bot_data={"owners": {123}, "approvals": [{}]}, args=["0"])
        with patch("bot.download") as download:
            await bot.taxi(update(), context)
            download.assert_not_called()

    async def test_empty_list_never_downloads(self):
        context = SimpleNamespace(bot_data={"owners": {123}, "approvals": []}, args=[])
        with patch("bot.download") as download:
            await bot.taxi(update(), context)
            download.assert_not_called()

    async def test_non_owner_never_downloads(self):
        context = SimpleNamespace(bot_data={"owners": {123}, "approvals": [{}]}, args=[])
        with patch("bot.download") as download:
            await bot.taxi(update(456), context)
            download.assert_not_called()

    async def test_download_failure_is_redacted(self):
        context = SimpleNamespace(bot_data={"owners": {123}, "approvals": [{"video_id": "abcdefghijk"}]}, args=[])
        message = update()
        with patch("bot.download", side_effect=RuntimeError("TOKEN_SHOULD_STAY_SECRET")):
            await bot.taxi(message, context)
        text = str(message.effective_message.reply_text.call_args_list)
        self.assertNotIn("TOKEN_SHOULD_STAY_SECRET", text)
        message.effective_message.reply_audio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
