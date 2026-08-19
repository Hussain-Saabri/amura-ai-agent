from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from dotenv import load_dotenv
from routers.medicine_router import router as medicine_router
from routers.order_router import router as order_router
from db import check_db_connection

load_dotenv()

app = FastAPI(
    title="Amura Healthcare",
    description="This is the API documentation for Amura Healthcare.",
    version="1.0.0",
)

# Mount static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(medicine_router)
app.include_router(order_router)

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.on_event("startup")
def startup_db_check():
    check_db_connection()