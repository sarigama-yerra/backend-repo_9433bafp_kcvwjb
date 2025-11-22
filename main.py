import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Customer, Order, OrderItem

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------------

def to_str_id(doc):
    if not doc:
        return doc
    doc = dict(doc)
    if doc.get("_id"):
        doc["id"] = str(doc.pop("_id"))
    # convert nested ids if present
    if doc.get("items"):
        for it in doc["items"]:
            if isinstance(it.get("id"), ObjectId):
                it["id"] = str(it["id"])
    return doc


def compute_order_totals(order: Order) -> Order:
    # compute line totals
    subtotal = 0.0
    for item in order.items:
        item.line_total = round(item.unit_price * item.quantity, 2)
        subtotal += item.line_total
    order.subtotal = round(subtotal, 2)
    discount = 0.0
    if order.discount_type == "amount":
        discount = min(order.discount_value, order.subtotal)
    else:  # percent
        discount = round(order.subtotal * (order.discount_value / 100.0), 2)
        discount = min(discount, order.subtotal)
    order.total = round(max(order.subtotal - discount, 0.0), 2)
    return order


# ---------------------------------------------------------------------------------
# Health and info
# ---------------------------------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "Transactional CRUD Backend Ready"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------------------------------------------------------------------------------
# Customers CRUD
# ---------------------------------------------------------------------------------
@app.post("/api/customers")
def create_customer(payload: Customer):
    # enforce unique email
    existing = db.customer.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    customer_id = create_document("customer", payload)
    doc = db.customer.find_one({"_id": ObjectId(customer_id)})
    return to_str_id(doc)


@app.get("/api/customers")
def list_customers():
    docs = get_documents("customer", {})
    return [to_str_id(d) for d in docs]


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: str):
    doc = db.customer.find_one({"_id": ObjectId(customer_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return to_str_id(doc)


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None


@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: str, payload: CustomerUpdate):
    update_data = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update_data:
        return get_customer(customer_id)
    if "email" in update_data:
        # check uniqueness
        clash = db.customer.find_one({"email": update_data["email"], "_id": {"$ne": ObjectId(customer_id)}})
        if clash:
            raise HTTPException(status_code=400, detail="Email already exists")
    res = db.customer.update_one({"_id": ObjectId(customer_id)}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return get_customer(customer_id)


@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: str):
    # prevent delete if orders exist
    has_order = db.order.find_one({"customer_id": customer_id})
    if has_order:
        raise HTTPException(status_code=400, detail="Cannot delete customer with existing orders")
    res = db.customer.delete_one({"_id": ObjectId(customer_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {"ok": True}


# ---------------------------------------------------------------------------------
# Orders CRUD
# ---------------------------------------------------------------------------------
@app.post("/api/orders")
def create_order(payload: Order):
    # validate customer exists
    if not db.customer.find_one({"_id": ObjectId(payload.customer_id)}):
        raise HTTPException(status_code=400, detail="Invalid customer_id")
    order = compute_order_totals(payload)
    order_id = create_document("order", order)
    doc = db.order.find_one({"_id": ObjectId(order_id)})
    return to_str_id(doc)


@app.get("/api/orders")
def list_orders(customer_id: Optional[str] = None, status: Optional[str] = None):
    query = {}
    if customer_id:
        query["customer_id"] = customer_id
    if status:
        query["status"] = status
    docs = get_documents("order", query)
    return [to_str_id(d) for d in docs]


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    doc = db.order.find_one({"_id": ObjectId(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return to_str_id(doc)


class OrderUpdate(BaseModel):
    status: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = Field(None, ge=0)
    items: Optional[List[OrderItem]] = None


@app.put("/api/orders/{order_id}")
def update_order(order_id: str, payload: OrderUpdate):
    doc = db.order.find_one({"_id": ObjectId(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")

    # merge existing with updates via model
    current = Order(
        customer_id=doc["customer_id"],
        status=doc.get("status", "draft"),
        items=[OrderItem(**i) for i in doc.get("items", [])],
        discount_type=doc.get("discount_type", "amount"),
        discount_value=doc.get("discount_value", 0.0),
        subtotal=doc.get("subtotal", 0.0),
        total=doc.get("total", 0.0),
    )

    data = payload.model_dump(exclude_none=True)
    if "items" in data:
        current.items = data["items"]
    if "status" in data:
        current.status = data["status"]
    if "discount_type" in data:
        current.discount_type = data["discount_type"]
    if "discount_value" in data:
        current.discount_value = data["discount_value"]

    current = compute_order_totals(current)

    update_doc = current.model_dump()
    res = db.order.update_one({"_id": ObjectId(order_id)}, {"$set": update_doc})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return get_order(order_id)


@app.delete("/api/orders/{order_id}")
def delete_order(order_id: str):
    res = db.order.delete_one({"_id": ObjectId(order_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
