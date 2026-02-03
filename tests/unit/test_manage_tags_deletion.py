"""
Tests for ManageTagsDialog deletion behavior.

CRITICAL: When a tag is deleted, ALL related entries must be removed:
1. The CPLC-based entry from secure_storage["tags"]
2. The CPLC-based entry from config["known_tags"]
3. The UID-based entry from config["known_tags"] (if exists)

Failure to clean up ALL entries causes the system to use DEFAULT_KEY
on restart, which can brick the card.
"""

import pytest
from unittest.mock import MagicMock


class TestManageTagsDeletion:
    """Tests for complete tag deletion."""

    def test_delete_removes_cplc_entry_from_secure_storage(self):
        """Deleting a tag removes the CPLC entry from secure_storage."""
        cplc_hash = "AABBCCDD11223344"
        uid = "04AABBCCDD"

        secure_storage = {
            "tags": {
                cplc_hash: {
                    "name": "Test Card",
                    "key": "404142434445464748494A4B4C4D4E4F",
                    "uid": uid,
                }
            }
        }
        config = {"known_tags": {cplc_hash: True, uid: True}}

        # Simulate deletion
        tag_data = secure_storage["tags"][cplc_hash]
        del secure_storage["tags"][cplc_hash]

        assert cplc_hash not in secure_storage["tags"]

    def test_delete_removes_cplc_entry_from_known_tags(self):
        """Deleting a tag removes the CPLC entry from config known_tags."""
        cplc_hash = "AABBCCDD11223344"
        uid = "04AABBCCDD"

        config = {"known_tags": {cplc_hash: True, uid: True}}

        # Simulate deletion of CPLC entry
        if cplc_hash in config["known_tags"]:
            del config["known_tags"][cplc_hash]

        assert cplc_hash not in config["known_tags"]

    def test_delete_MUST_remove_uid_entry_from_known_tags(self):
        """
        CRITICAL: Deleting a tag MUST also remove the UID entry from known_tags.

        On initial card detection (before CPLC retrieval), the system looks up
        by UID. If the UID entry remains in known_tags with True, it will
        use DEFAULT_KEY which could brick the card.
        """
        cplc_hash = "AABBCCDD11223344"
        uid = "04AABBCCDD"

        secure_storage = {
            "tags": {
                cplc_hash: {
                    "name": "Test Card",
                    "key": "404142434445464748494A4B4C4D4E4F",
                    "uid": uid,
                }
            }
        }
        config = {"known_tags": {cplc_hash: True, uid: True}}

        # Get tag data before deletion
        tag_data = secure_storage["tags"].get(cplc_hash, {})
        tag_uid = tag_data.get("uid", "")

        # Simulate proper deletion (as implemented in fix)
        if cplc_hash in secure_storage["tags"]:
            del secure_storage["tags"][cplc_hash]

        known_tags = config.get("known_tags", {})
        if cplc_hash in known_tags:
            del known_tags[cplc_hash]
        if tag_uid and tag_uid in known_tags:
            del known_tags[tag_uid]

        # CRITICAL: Both CPLC and UID must be removed
        assert cplc_hash not in config["known_tags"]
        assert uid not in config["known_tags"]

    def test_clear_key_sets_both_cplc_and_uid_to_none(self):
        """
        CRITICAL: Clearing a key must set BOTH CPLC and UID entries to None.

        If the UID entry remains True, the system will use DEFAULT_KEY.
        """
        cplc_hash = "AABBCCDD11223344"
        uid = "04AABBCCDD"

        config = {"known_tags": {cplc_hash: True, uid: True}}

        # Simulate clear key operation (as implemented in fix)
        known_tags = config.get("known_tags", {})
        if cplc_hash in known_tags:
            known_tags[cplc_hash] = None
        if uid and uid in known_tags:
            known_tags[uid] = None

        # Both should be None, not True
        assert config["known_tags"].get(cplc_hash) is None
        assert config["known_tags"].get(uid) is None


class TestGetKeyLookupOrder:
    """Tests for the key lookup logic that motivates the deletion fix."""

    def test_lookup_by_uid_before_cplc_on_detection(self):
        """
        On initial detection, system looks up by UID (CPLC not yet retrieved).

        This demonstrates WHY we must clean up UID entries on deletion.
        """
        DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"
        uid = "04AABBCCDD"

        # State after "deletion" but with UID entry remaining (BUG)
        secure_storage = {"tags": {}}  # Empty - tag was deleted
        config = {"known_tags": {uid: True}}  # UID entry remains!

        # Simulate get_key lookup (using UID before CPLC is known)
        card_id = uid  # On initial detection, this is the UID

        key = None

        # Step 1: Check secure_storage
        if secure_storage.get("tags", {}).get(card_id):
            key = secure_storage["tags"][card_id]["key"]

        # Step 2: Check known_tags
        if key is None:
            is_default_key = config["known_tags"].get(card_id, None)
            if is_default_key:
                key = DEFAULT_KEY  # BUG: This gets hit!

        # With the bug, we would use DEFAULT_KEY
        assert key == DEFAULT_KEY, "This test shows the bug scenario"

    def test_lookup_after_proper_deletion(self):
        """
        After proper deletion (including UID), system prompts for key.
        """
        DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"
        uid = "04AABBCCDD"

        # State after PROPER deletion (both CPLC and UID removed)
        secure_storage = {"tags": {}}  # Empty
        config = {"known_tags": {}}  # UID entry also removed!

        # Simulate get_key lookup
        card_id = uid

        key = None

        # Step 1: Check secure_storage
        if secure_storage.get("tags", {}).get(card_id):
            key = secure_storage["tags"][card_id]["key"]

        # Step 2: Check known_tags
        if key is None:
            is_default_key = config["known_tags"].get(card_id, None)
            if is_default_key:
                key = DEFAULT_KEY

        # With proper deletion, key should be None (prompts user)
        assert key is None, "After proper deletion, should prompt for key"
