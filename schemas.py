"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal

# -----------------------------------------------------------------------------
# Domain schemas for transactional CRUD demo
# -----------------------------------------------------------------------------

class Customer(BaseModel):
    """Customers collection schema (collection name: customer)"""
    name: str = Field(..., description="Full name of the customer")
    email: str = Field(..., description="Unique email address")
    phone: Optional[str] = Field(None, description="Phone number")
    address: Optional[str] = Field(None, description="Mailing address")
    status: Literal["active", "inactive"] = Field("active", description="Customer status")

class OrderItem(BaseModel):
    """Embedded model used inside orders.items"""
    id: Optional[str] = Field(None, description="Client-generated line id")
    product_name: str = Field(..., description="Name/description of the item")
    unit_price: float = Field(..., ge=0, description="Unit price")
    quantity: int = Field(..., ge=1, description="Quantity ordered")
    line_total: Optional[float] = Field(None, ge=0, description="Computed: unit_price * quantity")

class Order(BaseModel):
    """Orders collection schema (collection name: order)"""
    customer_id: str = Field(..., description="Reference to customer _id")
    status: Literal["draft", "pending", "paid", "shipped", "cancelled"] = Field(
        "draft", description="Order lifecycle status"
    )
    items: List[OrderItem] = Field(default_factory=list, description="Line items")
    discount_type: Literal["amount", "percent"] = Field("amount", description="Discount type")
    discount_value: float = Field(0.0, ge=0, description="Discount amount in currency or percent value")
    subtotal: float = Field(0.0, ge=0, description="Computed sum of line totals")
    total: float = Field(0.0, ge=0, description="Computed subtotal minus discount (min 0)")

# -----------------------------------------------------------------------------
# Example schemas kept for reference
# -----------------------------------------------------------------------------

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
