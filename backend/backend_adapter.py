from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="University Student Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "University Student Platform API", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "backend"}

@app.post("/api/analyze")
async def analyze_file():
    return {"message": "Analysis endpoint ready", "status": "success"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
