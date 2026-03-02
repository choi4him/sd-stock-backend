cat >> app/models/orders.py << 'EOL'

class OrderUpdate(BaseModel):
    confirmed_quantity: Optional[int] = Field(None, gt=0)
    extra_quantity: Optional[int] = None
    delivery_date: Optional[date] = None
    stage: Optional[OrderStageEnum] = None
    customer_id: Optional[UUID] = None
    strain_id: Optional[UUID] = None
    age_week: Optional[int] = None
    sex: Optional[str] = None
EOL
