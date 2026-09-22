from fastapi import FastAPI
from dotenv import load_dotenv
from routers.medicine_router import router as medicine_router
from routers.order_router import router as order_router
from db import check_db_connection
from pyngrok import ngrok
load_dotenv()

app = FastAPI(
    title="Amura Healthcare",
    description="This is the API documentation for Amura Healthcare Voice AI Agent.",
    version="1.0.0",
)

# Include Routers
app.include_router(medicine_router)
app.include_router(order_router)

@app.get("/")
def root():
    return {"message": "Amura Healthcare Voice AI Agent is running"}

import os


@app.on_event("startup")
async def startup_db_check():
    await check_db_connection()
    port = int(os.environ.get("PORT", 8000))
    public_url = ngrok.connect(port).public_url
    print(f"ngrok tunnel \"{public_url}\" -> \"http://127.0.0.1:{port}\"")
    




