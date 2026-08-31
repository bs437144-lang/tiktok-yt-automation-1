import argparse
import sys
import os
import logging
from dotenv import load_dotenv
from src.orchestrator import execute_slot

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/runner.log", encoding="utf-8")
    ]
)

logger = logging.getLogger("main")

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="TikTok to YouTube Shorts Automation Runner")
    parser.add_argument("--slot", type=int, required=True, help="Slot number (1 or 2)")
    parser.add_argument("--channel", type=str, required=True, help="Channel ID as defined in channels.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Run without actually uploading to YouTube or modifying production DB")

    args = parser.parse_args()

    # Allow environment override for DRY_RUN
    dry_run = args.dry_run or (os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes"))

    logger.info(f"Starting automation run: Channel={args.channel}, Slot={args.slot}, DryRun={dry_run}")

    try:
        result = execute_slot(args.channel, args.slot, dry_run=dry_run)
        logger.info(f"Execution finished with result: {result}")
        if result.get("status") in ("success", "skipped", "no_content", "disabled"):
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        logger.exception(f"Unhandled exception during execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
