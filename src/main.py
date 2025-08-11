"""
Entry point for the Moomoo ChatGPT Trader backend.

This module exposes a FastAPI application that will serve as the API for controlling the trading bot.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Moomoo ChatGPT Trader",
    description="Backend API for the ChatGPT-powered trading bot using the moomoo API.",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    """Health-check endpoint for the API."""
    return {"message": "Moomoo ChatGPT Trader API is running."}


# Additional API routes for strategies, configuration, and trade history will be added here.


if __name__ == "__main__":
    import uvicorn

    # Running the app using uvicorn for local development
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
