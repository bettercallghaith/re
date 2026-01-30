"""
Sales Analytics API - Hybrid Approach
Uses robust PDF parsing for immediate data + Ollama (Mistral) for analysis.
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
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"


async def call_llm(prompt: str, system_prompt: str = "") -> str:
    """Call Ollama LLM with a prompt"""
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp for accuracy
                "num_predict": 1000  # Reduced for speed
            }
        }
        try:
            async with session.post(OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
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
            text = page.extract_text() or ""
            all_text.append(text)
    return "\n".join(all_text)


def extract_number_from_text(text: str) -> float:
    """Extract a clean number from text, handling commas and decimals"""
    # First, handle cases where space is used as thousands separator (common in some regions)
    # Convert "1 150.00" to "1150.00"
    cleaned_text = re.sub(r'(\d+)\s+(\d{3})(?:\.\d{2})?', r'\1\2', text)
    
    # Find all number patterns (handles 1,150.00 and 1150.00 format)
    matches = re.findall(r'(\d{1,3}(?:(?:,|\s)\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)', text)
    
    if matches:
        # Take the last match (usually the value)
        value_str = matches[-1]
        # Remove commas and spaces
        cleaned = value_str.replace(',', '').replace(' ', '')
        try:
            return float(cleaned)
        except:
            return 0.0
    return 0.0


def extract_summary_from_pdf(pdf_content: bytes) -> Dict[str, float]:
    """Extract summary financial values using robust regex"""
    summary = {
        'total_orders_value': 0.0,
        'cash': 0.0,
        'bank': 0.0,
        'delivery_charge': 0.0,
        'pending': 0.0,
        'refund': 0.0,
        'return': 0.0,
        'cancel': 0.0
    }
    
    keywords_map = {
        'total orders': 'total_orders_value',
        'cash': 'cash',
        'bank': 'bank',
        'delivery charge': 'delivery_charge',
        'pending': 'pending',
        'refund': 'refund',
        'return': 'return',
        'cancel': 'cancel'
    }
    
    def process_pair(label_text: str, value_text: str):
        label_lower = label_text.lower().strip()
        for keyword, key in keywords_map.items():
            if keyword in label_lower:
                val = extract_number_from_text(value_text)
                if val > 0:
                    summary[key] = val

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            # 1. Check plain text lines (often best for Summary box)
            text = page.extract_text() or ''
            lines = text.split('\n')
            for line in lines:
                line_lower = line.lower().strip()
                for keyword, key in keywords_map.items():
                    if keyword in line_lower:
                        val = extract_number_from_text(line)
                        if val > 0:
                            summary[key] = val
                            
            # 2. Check tables (carefully)
            tables = page.extract_tables()
            for table in tables:
                if not table: continue
                for row in table:
                    if not row or len(row) < 2: continue
                    
                    label_cell = str(row[0] or '').strip()
                    value_cell = str(row[1] or '').strip()
                    
                    # Split multiline cells (Fixes merged cell bug)
                    labels = label_cell.split('\n')
                    values = value_cell.split('\n')
                    
                    # Only process if lines align, or strict 1-to-1
                    if len(labels) == len(values) and len(labels) > 1:
                        for l, v in zip(labels, values):
                            process_pair(l, v)
                    elif len(labels) == 1:
                        # Simple row
                        process_pair(label_cell, value_cell)
                    else:
                        # Mismatch or merged label with single value? 
                        # DANGER: Do not assume single value applies to all labels.
                        # Try to see if value_cell has newlines that were lost or if it's just one block
                        # If label has multiple lines, better to trust text extraction for this part.
                        pass
                                
    return summary


def extract_orders_from_pdf(pdf_content: bytes) -> List[Dict[str, Any]]:
    """Extract individual orders using robust table parsing"""
    orders = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table: continue
                
                # Heuristic: check if this looks like the main data table
                # Usually has many columns (Date, Order No, etc.)
                for row in table:
                    if not row or len(row) < 5: continue
                    
                    # Columns usually: [0]Date [1]OrderNo [2]Area [3]Phone [4]Product [5]Price [6]Qty [7]Payment [8]Status
                    # Check date format in first col
                    date_val = str(row[0] or '').strip()
                    if not re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_val):
                        continue
                        
                    try:
                        order = {
                            'date': date_val,
                            'order_no': str(row[1] or '').strip() if len(row) > 1 else '',
                            'area': str(row[2] or '').strip() if len(row) > 2 else '',
                            'customer_no': str(row[3] or '').strip() if len(row) > 3 else '',
                            'product': str(row[4] or '').strip() if len(row) > 4 else '',
                            'unit_price': str(row[5] or '').strip() if len(row) > 5 else '0',
                            # Skip quantity (index 6) as per request - unit_price has total
                            'payment': str(row[7] or '').strip() if len(row) > 7 else '',
                            'status': str(row[8] or 'COMPLETED').strip() if len(row) > 8 else 'COMPLETED'
                        }
                        orders.append(order)
                    except Exception:
                        continue
    return orders


def parse_currency_str(value: str) -> float:
    """Helper to parse currency strings from the orders table"""
    return extract_number_from_text(value)


async def generate_insights_with_llm(summary: Dict, orders_count: int, top_products: List[str], top_areas: List[str]) -> str:
    """Generate concise AI insights (this is the only slow part, but runs last)"""
    
    system_prompt = """You are a Retail Business Analyst. Provide exactly 4 concise, actionable insights.
Start each with an emoji. Max 2 sentences each. Focus on sales trends, geography, and product performance."""

    prompt = f"""Analyze this Sales Data:
- Total Sales: {summary.get('total_orders_value', 0):,.0f}
- Net Profit: {summary.get('total_profit', 0):,.0f}
- Cancellations: {summary.get('cancel_amount', 0):,.0f}
- Orders Count: {orders_count}
- Top Products: {', '.join(top_products[:5])}
- Top Areas: {', '.join(top_areas[:3])}

Provide 4 insights (📈, ⚠️, 🗺️, 💡):"""

    response = await call_llm(prompt, system_prompt)
    if not response:
        return "📈 Sales detected. Check daily trends.\n⚠️ Review cancellations.\n🗺️ Focus on top areas.\n💡 Promote top products."
    return response


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/analyze")
async def analyze_sales(file: UploadFile = File(...)):
    """Analyze PDF: Text Extraction (Fast) + LLM Insights (Slow)"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    content = await file.read()
    
    # 1. FAST EXTRACTION
    # Extract summary financials
    pdf_summary = extract_summary_from_pdf(content)
    
    # Extract orders
    orders = extract_orders_from_pdf(content)
    
    if not orders and pdf_summary['total_orders_value'] == 0:
         raise HTTPException(status_code=400, detail="Could not extract data. Please ensure PDF format is correct.")

    # 2. CALCULATIONS
    df = pd.DataFrame(orders)
    
    if not df.empty:
        df['revenue'] = df['unit_price'].apply(parse_currency_str)
        # Fallback if revenue is 0 but we have valid price string
        if df['revenue'].sum() == 0 and not df.empty:
             # Try stricter parsing if needed, but extract_number_from_text is robust
             pass
    else:
        df = pd.DataFrame(columns=['revenue', 'customer_no', 'product', 'area', 'status', 'date'])

    # Use PDF summary totals if found, else calculate from table
    total_sales = pdf_summary['total_orders_value']
    if total_sales == 0 and not df.empty:
        total_sales = df['revenue'].sum()

    # Deductions
    delivery_charge = pdf_summary['delivery_charge']
    refund_amount = pdf_summary['refund']
    return_amount = pdf_summary['return']
    cancel_amount = pdf_summary['cancel']
    pending_amount = pdf_summary['pending']
    
    total_deductions = delivery_charge + refund_amount + return_amount + cancel_amount
    total_profit = total_sales - total_deductions
    profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
    
    total_orders = len(orders)
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # 3. DERIVED ANALYTICS
    biggest_orders = []
    top_customers = {}
    top_products = {}
    top_products_revenue = {}
    area_performance = {}
    status_counts = {}
    daily_trend = {}
    
    if not df.empty:
        # Biggest orders
        biggest = df.nlargest(5, 'revenue')
        biggest_orders = biggest[['customer_no', 'product', 'revenue', 'date']].to_dict('records')
        
        # Rankings
        if 'customer_no' in df.columns:
            top_customers = df.groupby('customer_no')['revenue'].sum().sort_values(ascending=False).head(10).to_dict()
        
        if 'product' in df.columns:
            top_products = df['product'].value_counts().head(10).to_dict()
            top_products_revenue = df.groupby('product')['revenue'].sum().sort_values(ascending=False).head(10).to_dict()
            
        if 'area' in df.columns:
            area_performance = df.groupby('area')['revenue'].sum().sort_values(ascending=False).head(8).to_dict()
            
        if 'status' in df.columns:
            status_counts = df['status'].value_counts().to_dict()
            
        # Daily
        if 'date' in df.columns:
            df['parsed_date'] = pd.to_datetime(df['date'], format='%d/%m/%Y', errors='coerce')
            daily = df.groupby(df['parsed_date'].dt.strftime('%Y-%m-%d'))['revenue'].sum()
            daily_trend = {k: int(v) for k, v in daily.to_dict().items() if k and k != 'NaT'}

    cancelled_orders = sum(v for k, v in status_counts.items() if 'cancel' in str(k).lower())
    successful_orders = total_orders - cancelled_orders
    
    # 4. LLM INSIGHTS (The only slow part)
    # Add profit to summary for LLM context
    pdf_summary['total_profit'] = total_profit
    
    llm_insights = await generate_insights_with_llm(
        pdf_summary,
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
        "top_customers": {k: int(v) for k, v in top_customers.items()},
        "top_products": top_products,
        "top_products_revenue": {k: int(v) for k, v in top_products_revenue.items()},
        "payment_methods": status_counts,
        "area_performance": {k: int(v) for k, v in area_performance.items()},
        "daily_trend": daily_trend,
        "llm_insights": llm_insights,
        "raw_data": orders[:100]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
