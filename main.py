from fastapi import FastAPI

app = FastAPI(
    title="Amura Healthcare",
    description="This is the API documentation for Amura Healthcare.",
    version="1.0.0",
)


@app.get("/")
def root():
    return "Hello AI Agent"


