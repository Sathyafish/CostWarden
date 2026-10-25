"""Lambda entry point for the API (behind a function URL). CORS is handled by the FastAPI app,
so the function URL itself must not also set CORS headers."""
from mangum import Mangum

from costwarden.api.app import create_app

handler = Mangum(create_app(), lifespan="off")
