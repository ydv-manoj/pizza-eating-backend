from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Firebase
firebase_credentials = os.getenv("FIREBASE_CREDENTIALS")
if not firebase_credentials:
    raise ValueError("Firebase credentials not found. Please set the FIREBASE_CREDENTIALS environment variable.")

cred = credentials.Certificate(json.loads(firebase_credentials))
firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class User(BaseModel):
    name: str
    age: int
    gender: str

class Pizza(BaseModel):
    userId: str

class PizzaLog(BaseModel):
    userId: str

class LeaderboardEntry(BaseModel):
    userId: str
    name: str
    pizzasEaten: int
    rank: int

# API routes
@app.post("/users")
async def create_user(user: User):
    doc_ref = db.collection("users").document()
    user_data = user.dict()
    user_data["coins"] = 500
    user_data["pizzasEaten"] = 0
    user_data["pizzaSlices"] = 0
    doc_ref.set(user_data)
    return {"id": doc_ref.id, **user_data}

@app.get("/users")
async def get_users():
    users = db.collection("users").stream()
    return [{"id": user.id, **user.to_dict()} for user in users]

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = db.collection("users").document(user_id).get()
    if not user.exists:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, **user.to_dict()}

@app.put("/users/{user_id}")
async def update_user(user_id: str, user: User):
    user_ref = db.collection("users").document(user_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")
    user_ref.update(user.dict())
    return {"message": "User updated successfully"}

@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    user_ref = db.collection("users").document(user_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")
    user_ref.delete()
    return {"message": "User deleted successfully"}

@app.post("/pizzas")
async def buy_pizza(pizza: Pizza):
    user_ref = db.collection("users").document(pizza.userId)
    user = user_ref.get()
    if not user.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user.to_dict()
    if user_data["coins"] < 10:  # Assuming each pizza slice costs 10 coins
        raise HTTPException(status_code=400, detail="Not enough coins")
    
    user_ref.update({
        "coins": user_data["coins"] - 10,
        "pizzaSlices": user_data["pizzaSlices"] + 1
    })
    
    return {"message": "Pizza slice purchased successfully"}

@app.post("/log-pizza")
async def log_pizza(pizza_log: PizzaLog):
    user_ref = db.collection("users").document(pizza_log.userId)
    user = user_ref.get()
    if not user.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user.to_dict()
    if user_data["pizzaSlices"] < 1:
        raise HTTPException(status_code=400, detail="No pizza slices available to log")
    
    user_ref.update({
        "pizzaSlices": user_data["pizzaSlices"] - 1,
        "pizzasEaten": user_data["pizzasEaten"] + 1
    })
    
    # Log the pizza eating timestamp
    db.collection("pizza_history").add({
        "userId": pizza_log.userId,
        "timestamp": datetime.now()
    })
    
    # Update leaderboard
    update_leaderboard()
    
    return {"message": "Pizza logged successfully"}

@app.get("/pizza-history/{user_id}")
async def get_pizza_history(user_id: str):
    history = db.collection("pizza_history").where("userId", "==", user_id).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    return [{"id": entry.id, "timestamp": entry.to_dict()["timestamp"].isoformat()} for entry in history]

@app.get("/leaderboard")
async def get_leaderboard():
    leaderboard = db.collection("users").order_by("pizzasEaten", direction=firestore.Query.DESCENDING).limit(10).stream()
    return [entry.to_dict() for entry in leaderboard]

def update_leaderboard():
    users = db.collection("users").order_by("pizzasEaten", direction=firestore.Query.DESCENDING).stream()
    leaderboard_ref = db.collection("leaderboard")
    
    for rank, user in enumerate(users, start=1):
        user_data = user.to_dict()
        leaderboard_ref.document(user.id).set({
            "userId": user.id,
            "name": user_data["name"],
            "pizzasEaten": user_data["pizzasEaten"],
            "rank": rank
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
