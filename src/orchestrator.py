import os
import logging
from src.config import get_channel_by_id, load_config
from src.db import Database
from src.channel_runner import ChannelRunner

logger = logging.getLogger("orchestrator")

def execute_slot(channel_id: str, slot: int, dry_run: bool = False):
    config = get_channel_by_id(channel_id)
    if not config:
        raise ValueError(f"Channel '{channel_id}' not found in channels.yaml")

    if not config.enabled:
        logger.info(f"Channel '{channel_id}' is disabled. Skipping.")
        return {"status": "disabled"}

    db_path = f"data/{channel_id}.db"
    db = Database(db_path)

    runner = ChannelRunner(config, db, dry_run=dry_run)
    result = runner.run_slot(slot)

    # Clean DB WAL before Git push (Section 4)
    db.checkpoint_wal()
    return result
