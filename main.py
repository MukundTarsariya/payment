from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
import os
from typing import Optional, List
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://payment-ui-ten.vercel.app"],  # Allow your Angular app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Connect to MongoDB
client = MongoClient("mongodb+srv://mukundtarsariya1998:07qKnZiysC8OsCB1@payment.9jbkg.mongodb.net/?retryWrites=true&w=majority&appName=Payment")
db = client['payment_db']
collection = db['payments']

# Directory to store evidence files
evidence_dir = "evidence_files"
os.makedirs(evidence_dir, exist_ok=True)

# Helper function to calculate total_due
def calculate_total_due(due_amount, discount_percent, tax_percent):
    return round(due_amount * (1 - discount_percent / 100) * (1 + tax_percent / 100), 2)

# Web service to fetch payments with filtering, searching, and paging
@app.get("/payments")
async def get_payments(
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 10
):
    today = datetime.utcnow().date()
    query = {}

    # Filter by status
    if status:
        query['payee_payment_status'] = status

    # Search by name or email
    if search:
        query['$or'] = [
            {'payee_first_name': {'$regex': search, '$options': 'i'}},
            {'payee_last_name': {'$regex': search, '$options': 'i'}},
            {'payee_email': {'$regex': search, '$options': 'i'}}
        ]

    payments = []
    for payment in collection.find(query).skip(skip).limit(limit):
        # Update payment status based on due date
        if payment['payee_payment_status'] != 'completed':
            if payment['payee_due_date'].date() == today:
                payment['payee_payment_status'] = 'due_now'
            elif payment['payee_due_date'].date() < today:
                payment['payee_payment_status'] = 'overdue'
        
        # Calculate total_due
        payment['total_due'] = calculate_total_due(
            payment['due_amount'],
            payment.get('discount_percent', 0),
            payment.get('tax_percent', 0)
        )
        
        # Convert ObjectId to string
        payment['_id'] = str(payment['_id'])
        
        payments.append(payment)
    
    return payments

# Web service to update a payment
@app.put("/payments/{payment_id}")
async def update_payment(payment_id: str, update_data: dict):
    # Convert payee_due_date to a datetime object
    if 'payee_due_date' in update_data:
        update_data['payee_due_date'] = datetime.fromisoformat(update_data['payee_due_date'].replace('Z', '+00:00'))

    result = collection.update_one({"_id": ObjectId(payment_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"message": "Payment updated successfully"}

# Web service to delete a payment
@app.delete("/payments/{payment_id}")
async def delete_payment(payment_id: str):
    result = collection.delete_one({"_id": ObjectId(payment_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"message": "Payment deleted successfully"}

# Web service to create a new payment
@app.post("/payments")
async def create_payment(payment_data: dict):
    # Calculate total_due
    payment_data['total_due'] = calculate_total_due(
        payment_data['due_amount'],
        payment_data.get('discount_percent', 0),
        payment_data.get('tax_percent', 0)
    )
    # Convert date strings to datetime objects
    
    
    payment_data['payee_added_date_utc'] = datetime.fromisoformat(payment_data['payee_added_date_utc'].replace('Z', '+00:00'))
    payment_data['payee_due_date'] = datetime.fromisoformat(payment_data['payee_due_date'].replace('Z', '+00:00'))
    result = collection.insert_one(payment_data)
    return {"id": str(result.inserted_id)}

@app.post("/payments/{payment_id}/upload_evidence")
async def upload_evidence(payment_id: str, file: UploadFile = File(...)):
    # Check file type
    if file.content_type not in ["application/pdf", "image/png", "image/jpeg"]:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Save the file temporarily
    file_path = os.path.join(evidence_dir, f"{payment_id}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    # Update payment status and store file path in MongoDB
    result = collection.update_one(
        {"_id": ObjectId(payment_id)},
        {"$set": {"payee_payment_status": "completed", "evidence_file": file_path}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {"message": "Evidence uploaded successfully", "file_path": file_path}

# Web service to download evidence
@app.get("/payments/{payment_id}/download_evidence")
async def download_evidence(payment_id: str):
    payment = collection.find_one({"_id": ObjectId(payment_id)})
    if not payment or "evidence_file" not in payment:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    file_path = payment["evidence_file"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)

# Web service to fetch a single payment by ID
@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    payment = collection.find_one({"_id": ObjectId(payment_id)})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Calculate total_due
    payment['total_due'] = calculate_total_due(
        payment['due_amount'],
        payment.get('discount_percent', 0),
        payment.get('tax_percent', 0)
    )
    
    # Convert ObjectId to string
    payment['_id'] = str(payment['_id'])
    
    return payment
