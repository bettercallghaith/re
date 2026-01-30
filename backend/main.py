"""
Sales Analytics API - LLM-Powered PDF Extraction
Uses Ollama (Mistral) to intelligently extract and analyze sales data from ANY PDF format.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Dict, List, Any, Optional
import pdfplumber
import pandas as pd
import aiohttp
import io
import os
import re
import json

app = FastAPI(title="Sales Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"


async def call_llm(prompt: str, system_prompt: str = "") -> str:
    """Call Ollama LLM with a prompt"""
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": "mistral",
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp for accuracy
                "num_predict": 4000
            }
        }
        try:
            async with session.post(OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "")
                return ""
        except Exception as e:
            print(f"LLM call failed: {e}")
            return ""


def extract_all_text_from_pdf(pdf_content: bytes) -> str:
    """Extract all text from PDF including tables"""
    all_text = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = f"\n--- PAGE {i+1} ---\n"
            
            # Extract text
            text = page.extract_text() or ""
            page_text += text + "\n"
            
            # Extract tables
            tables = page.extract_tables()
            for table_idx, table in enumerate(tables):
                if table:
                    page_text += f"\n[TABLE {table_idx+1}]\n"
                    for row in table:
                        if row:
                            row_text = " | ".join(str(cell or "") for cell in row)
                            page_text += row_text + "\n"
            
            all_text.append(page_text)
    
    return "\n".join(all_text)


def extract_json_from_response(response: str) -> dict:
    """Extract JSON from LLM response"""
    # Try to find JSON in the response
    json_patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'\{[\s\S]*\}'
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            for match in matches:
                try:
                    # Clean the match
                    cleaned = match.strip()
                    if not cleaned.startswith('{'):
                        continue
                    return json.loads(cleaned)
                except:
                    continue
    
    return {}


async def extract_summary_with_llm(pdf_text: str) -> Dict[str, Any]:
    """Use LLM to extract summary data from PDF"""
    
    system_prompt = """You are a data extraction expert. Extract financial data from sales reports with 100% accuracy.
Your task is to find and extract specific values from the text.
CRITICAL: Extract the EXACT numbers as they appear. Do not calculate or modify them.
Return ONLY valid JSON, no other text."""

    prompt = f"""Analyze this sales report and extract the financial summary data.

REPORT TEXT:
{pdf_text[:15000]}  # Limit to avoid token issues

Extract and return this JSON structure (use 0 if not found):
```json
{{
    "total_orders_value": <number - find "TOTAL ORDERS" value>,
    "cash": <number - find "CASH" value>,
    "bank": <number - find "BANK" value>,
    "delivery_charge": <number - find "DELIVERY CHARGE" value>,
    "pending": <number - find "PENDING" value>,
    "refund": <number - find "REFUND" value>,
    "return": <number - find "RETURN" value>,
    "cancel": <number - find "CANCEL" value>
}}
```

Remember: Extract exact values like 183,600.00 → 183600, 1,150.00 → 1150
Return ONLY the JSON:"""

    response = await call_llm(prompt, system_prompt)
    data = extract_json_from_response(response)
    
    # Provide defaults
    defaults = {
        'total_orders_value': 0,
        'cash': 0,
        'bank': 0,
        'delivery_charge': 0,
        'pending': 0,
        'refund': 0,
        'return': 0,
        'cancel': 0
    }
    
    for key in defaults:
        if key not in data:
            data[key] = defaults[key]
        else:
            # Ensure it's a number
            try:
                data[key] = float(str(data[key]).replace(',', ''))
            except:
                data[key] = 0
    
    return data


async def extract_orders_with_llm(pdf_text: str) -> List[Dict[str, Any]]:
    """Use LLM to extract individual orders from PDF"""
    
    system_prompt = """You are a data extraction expert. Extract sales order data from reports.
Each order has: date, order number, area/location, customer phone, product name, price, and status.
Return valid JSON array only."""

    prompt = f"""Extract the individual sales orders from this report.

REPORT TEXT:
{pdf_text[:20000]}

Extract and return a JSON array of orders. Each order should have:
- date: DD/MM/YYYY format
- order_no: order number
- area: location/area name
- customer_no: customer phone number
- product: product name
- unit_price: price as number (183600.00 → 183600)
- status: order status (e.g., PENDING, CASH, CANCELLED, etc.)

Return ONLY the JSON array:
```json
[
    {{
        "date": "28/01/2026",
        "order_no": "12345",
        "area": "Qatar",
        "customer_no": "97455060363",
        "product": "Product Name",
        "unit_price": 1500,
        "status": "PENDING"
    }}
]
```"""

    response = await call_llm(prompt, system_prompt)
    data = extract_json_from_response(response)
    
    # Handle if it's a dict with an array inside
    if isinstance(data, dict):
        for key in ['orders', 'data', 'items']:
            if key in data and isinstance(data[key], list):
                return data[key]
        return []
    
    if isinstance(data, list):
        return data
    
    return []


async def generate_insights_with_llm(summary: Dict, orders_count: int, top_products: List[str], top_areas: List[str]) -> str:
    """Generate AI insights about the sales data"""
    
    system_prompt = """You are a Qatar retail business analyst. Provide exactly 4 concise, actionable insights based on the sales data.
Each insight must be 1-2 sentences maximum. Start each with an emoji."""

    prompt = f"""Analyze this Qatar sales report and provide 4 business insights:

Data:
- Total Sales: QAR {summary.get('total_orders_value', 0):,.0f}
- Cash Sales: QAR {summary.get('cash', 0):,.0f}
- Bank Sales: QAR {summary.get('bank', 0):,.0f}
- Delivery Charges: QAR {summary.get('delivery_charge', 0):,.0f}
- Pending Orders: QAR {summary.get('pending', 0):,.0f}
- Refunds: QAR {summary.get('refund', 0):,.0f}
- Returns: QAR {summary.get('return', 0):,.0f}
- Cancelled: QAR {summary.get('cancel', 0):,.0f}
- Number of Orders: {orders_count}
- Top Products: {', '.join(top_products[:5])}
- Top Areas: {', '.join(top_areas[:3])}

Provide 4 bullet points starting with emojis (📈, ⚠️, 🗺️, 💡):"""

    response = await call_llm(prompt, system_prompt)
    
    if not response:
        # Fallback insights
        return """📈 Sales data analyzed. Monitor daily trends for consistency.
⚠️ Review refunds and cancellations to identify issues.
🗺️ Focus marketing efforts on top-performing areas.
💡 Consider loyalty programs to increase repeat purchases."""
    
    return response


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/analyze")
async def analyze_sales(file: UploadFile = File(...)):
    """Analyze uploaded sales report PDF using LLM"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    content = await file.read()
    
    # Extract text from PDF
    pdf_text = extract_all_text_from_pdf(content)
    
    if not pdf_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")
    
    # Use LLM to extract summary data
    summary_data = await extract_summary_with_llm(pdf_text)
    
    # Use LLM to extract individual orders
    orders = await extract_orders_with_llm(pdf_text)
    
    if not orders:
        # Fallback: try regex-based extraction
        orders = extract_orders_fallback(content)
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(orders) if orders else pd.DataFrame()
    
    # Calculate values
    total_sales = summary_data.get('total_orders_value', 0)
    delivery_charge = summary_data.get('delivery_charge', 0)
    refund_amount = summary_data.get('refund', 0)
    return_amount = summary_data.get('return', 0)
    cancel_amount = summary_data.get('cancel', 0)
    pending_amount = summary_data.get('pending', 0)
    
    # Calculate profit: Total - (Delivery + Refund + Return + Cancel)
    total_deductions = delivery_charge + refund_amount + return_amount + cancel_amount
    total_profit = total_sales - total_deductions
    profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
    
    total_orders = len(orders) if orders else 0
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # Analyze orders
    biggest_orders = []
    top_customers = {}
    top_products = {}
    top_products_revenue = {}
    area_performance = {}
    status_counts = {}
    daily_trend = {}
    
    if not df.empty:
        # Parse unit_price
        if 'unit_price' in df.columns:
            df['revenue'] = pd.to_numeric(df['unit_price'], errors='coerce').fillna(0)
        else:
            df['revenue'] = 0
        
        # Top orders
        if 'revenue' in df.columns and df['revenue'].sum() > 0:
            biggest = df.nlargest(5, 'revenue')
            biggest_orders = biggest[['customer_no', 'product', 'revenue', 'date']].to_dict('records')
            for order in biggest_orders:
                order['revenue'] = int(order.get('revenue', 0))
        
        # Top customers
        if 'customer_no' in df.columns and 'revenue' in df.columns:
            top_customers = df.groupby('customer_no')['revenue'].sum().sort_values(ascending=False).head(10).to_dict()
            top_customers = {k: int(v) for k, v in top_customers.items()}
        
        # Top products by count
        if 'product' in df.columns:
            top_products = df['product'].value_counts().head(10).to_dict()
            # Top products by revenue
            if 'revenue' in df.columns:
                top_products_revenue = df.groupby('product')['revenue'].sum().sort_values(ascending=False).head(10).to_dict()
                top_products_revenue = {k: int(v) for k, v in top_products_revenue.items()}
        
        # Area performance
        if 'area' in df.columns and 'revenue' in df.columns:
            area_performance = df.groupby('area')['revenue'].sum().sort_values(ascending=False).head(8).to_dict()
            area_performance = {k: int(v) for k, v in area_performance.items()}
        
        # Status counts
        if 'status' in df.columns:
            status_counts = df['status'].value_counts().to_dict()
        
        # Daily trend
        if 'date' in df.columns and 'revenue' in df.columns:
            df['parsed_date'] = pd.to_datetime(df['date'], format='%d/%m/%Y', errors='coerce')
            daily = df.groupby(df['parsed_date'].dt.strftime('%Y-%m-%d'))['revenue'].sum()
            daily_trend = {k: int(v) for k, v in daily.to_dict().items() if k and k != 'NaT'}
    
    # Count cancelled orders
    cancelled_orders = sum(v for k, v in status_counts.items() if 'cancel' in str(k).lower())
    successful_orders = total_orders - cancelled_orders
    
    # Generate AI insights
    llm_insights = await generate_insights_with_llm(
        summary_data,
        total_orders,
        list(top_products.keys()),
        list(area_performance.keys())
    )
    
    return {
        "summary": {
            "total_sales": int(total_sales),
            "total_profit": int(total_profit),
            "delivery_charge": int(delivery_charge),
            "refund_amount": int(refund_amount),
            "return_amount": int(return_amount),
            "cancel_amount": int(cancel_amount),
            "pending_amount": int(pending_amount),
            "profit_margin": round(profit_margin, 1),
            "total_orders": total_orders,
            "avg_order_value": int(avg_order_value),
            "successful_orders": successful_orders,
            "cancelled_orders": cancelled_orders
        },
        "biggest_orders": biggest_orders,
        "top_customers": top_customers,
        "top_products": top_products,
        "top_products_revenue": top_products_revenue,
        "payment_methods": status_counts,
        "area_performance": area_performance,
        "daily_trend": daily_trend,
        "llm_insights": llm_insights,
        "raw_data": orders[:100] if orders else []
    }


def extract_orders_fallback(pdf_content: bytes) -> List[Dict[str, Any]]:
    """Fallback regex-based order extraction"""
    orders = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            for table in tables:
                if not table:
                    continue
                    
                for row in table:
                    if not row or len(row) < 4:
                        continue
                    
                    # Check if first column looks like a date
                    date_val = str(row[0] or '').strip()
                    if not re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_val):
                        continue
                    
                    order = {
                        'date': date_val,
                        'order_no': str(row[1] or '').strip() if len(row) > 1 else '',
                        'area': str(row[2] or '').strip() if len(row) > 2 else '',
                        'customer_no': str(row[3] or '').strip() if len(row) > 3 else '',
                        'product': str(row[4] or '').strip() if len(row) > 4 else '',
                        'unit_price': parse_price(str(row[5] or '')) if len(row) > 5 else 0,
                        'status': str(row[-1] or '').strip() if row else ''
                    }
                    orders.append(order)
    
    return orders


def parse_price(value: str) -> float:
    """Parse price string to float"""
    if not value:
        return 0
    # Remove currency symbols and spaces
    cleaned = re.sub(r'[^\d.,]', '', value)
    cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned) if cleaned else 0
    except:
        return 0


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
