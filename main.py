from fastapi import FastAPI
from dotenv import load_dotenv
from routers.medicine_router import router as medicine_router
from routers.order_router import router as order_router
from db import check_db_connection

load_dotenv()

app = FastAPI(
    title="Amura Healthcare",
    description="This is the API documentation for Amura Healthcare Voice AI Agent.",
    version="1.0.0",
)

# Include Routers
app.include_router(medicine_router)
app.include_router(order_router)
print("testing the branch")
@app.get("/")
def root():
    return {"message": "Amura Healthcare Voice AI Agent is running"}

@app.on_event("startup")
def startup_db_check():
    check_db_connection()