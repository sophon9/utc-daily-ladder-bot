"""Main FastAPI application."""
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.config import get_config_loader
from app.exchange import BybitClient
from app.bot import TradingBot
from app.database import get_database
from app.api import router, set_bot_instance, websocket_endpoint

# Load environment variables
load_dotenv()

# Get project root (parent of backend directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"

# Create logs and data directories if they don't exist
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "daily_ladder_bot.log"),
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

# Global instances
bot: TradingBot = None
client: BybitClient = None
database = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    global bot, client, database

    logger.info("Starting Daily Ladder Bot...")

    # Initialize database
    database = get_database()
    await database.init_db()

    # Load configuration
    config_path = PROJECT_ROOT / "config.json"
    config_loader = get_config_loader(str(config_path))
    config = config_loader.load()

    # Get API credentials
    api_key = os.getenv("BYBIT_API_KEY", "")
    api_secret = os.getenv("BYBIT_API_SECRET", "")

    if not api_key or not api_secret:
        logger.warning("API credentials not set. Using test mode.")

    # Initialize Bybit client
    client = BybitClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=config.use_testnet,
    )

    # Initialize trading bot
    bot = TradingBot(
        config=config,
        exchange_client=client,
        dry_run=config.dry_run,
        config_path=config_path,
    )

    await bot.initialize()

    # Set bot instance for API
    set_bot_instance(bot)

    logger.info("Daily Ladder Bot initialized successfully")
    logger.info(f"DRY_RUN: {config.dry_run}, TESTNET: {config.use_testnet}, BIAS: {config.bias}")

    # Restore previous running state (auto-starts if the bot was running before restart)
    await bot.restore_running_state()

    yield

    # Cleanup — pass save_state=False so we don't overwrite the user-set state.
    # This means a crash/SIGTERM restart will auto-resume if the bot was running.
    logger.info("Shutting down Daily Ladder Bot...")

    if bot and bot.running:
        await bot.stop(save_state=False)

    if client:
        await client.close()

    if database:
        await database.close()

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Daily Ladder Bot API",
    description="Automated trading bot for UTC daily-open drawdown entries with put hedges",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


# WebSocket endpoint
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket_endpoint(websocket, bot)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Daily Ladder Bot",
        "version": "1.0.0",
        "status": "running" if bot and bot.running else "stopped",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
