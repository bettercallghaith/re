from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import pdfplumber
import re
import io
import os
import aiohttp
from typing import List, Dict, Any
from datetime import datetime

app = FastAPI(title="Sales Analyzer API")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/api/generate"

# Telegram configuration (from environment)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


async def send_pdf_to_telegram(pdf_content: bytes, filename: str):
    """Send PDF file to Telegram chat"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        
        data = aiohttp.FormData()
        data.add_field('chat_id', TELEGRAM_CHAT_ID)
        data.add_field('document', pdf_content, filename=filename, content_type='application/pdf')
        data.add_field('caption', f"📊 New sales report uploaded: {filename}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    print(f"PDF sent to Telegram successfully: {filename}")
                else:
                    error = await response.text()
                    print(f"Telegram send failed: {error}")
    except Exception as e:
        print(f"Telegram error: {e}")


async def analyze_with_llm(prompt: str) -> str:
    """Call local Ollama LLM for analysis"""
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }
        try:
            async with session.post(OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "")
                return await generate_rule_based_insights(prompt)
        except Exception as e:
            print(f"LLM unavailable: {e}")
            return await generate_rule_based_insights(prompt)


async def generate_rule_based_insights(context: str) -> str:
    """Fallback rule-based analysis when LLM is unavailable"""
    insights = []
    
    # Parse metrics from context
    if "Total Sales:" in context:
        insights.append("📈 Strong sales performance detected. Monitor daily trends for consistency.")
    if "cancel" in context.lower():
        insights.append("⚠️ Review cancellation patterns to identify potential issues in order fulfillment.")
    if "area" in context.lower():
        insights.append("🗺️ Geographic analysis suggests focusing marketing on top-performing areas.")
    
    insights.append("💡 Consider implementing customer loyalty programs for repeat purchases.")
    
    return "\n".join(insights)


def extract_summary_from_pdf(pdf_content: bytes) -> Dict[str, float]:
    """Extract summary values (TOTAL ORDERS, DELIVERY CHARGE, REFUND, RETURN, CANCEL) from PDF"""
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
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            lines = text.split('\n')
            
            for line in lines:
                line_lower = line.lower().strip()
                for keyword, key in keywords_map.items():
                    if keyword in line_lower:
                        # Extract number from line
                        numbers = re.findall(r'[\d,]+\.?\d*', line)
                        if numbers:
                            # Take the last number (usually the value)
                            value_str = numbers[-1].replace(',', '')
                            try:
                                summary[key] = float(value_str)
                            except:
                                pass
            
            # Also try extracting from tables
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row in table:
                    if not row or len(row) < 2:
                        continue
                    cell_text = str(row[0] or '').lower().strip()
                    for keyword, key in keywords_map.items():
                        if keyword in cell_text:
                            value_str = str(row[1] or '').replace(',', '').replace('QAR', '').strip()
                            try:
                                summary[key] = float(value_str)
                            except:
                                pass
    
    return summary


def extract_sales_data(pdf_content: bytes) -> List[Dict[str, Any]]:
    """Extract sales data from PDF using pdfplumber"""
    orders = []
    
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            # Extract tables from each page
            tables = page.extract_tables()
            
            for table in tables:
                if not table:
                    continue
                    
                # Skip header row if detected
                start_row = 0
                if table[0] and any(h and 'date' in str(h).lower() for h in table[0]):
                    start_row = 1
                
                for row in table[start_row:]:
                    if not row or len(row) < 4:
                        continue
                    
                    # Try to parse as order data
                    try:
                        # Clean and extract values
                        date_val = str(row[0] or '').strip()
                        
                        # Skip if doesn't look like a date
                        if not re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_val):
                            continue
                        
                        order = {
                            'date': date_val,
                            'order_no': str(row[1] or '').strip() if len(row) > 1 else '',
                            'area': str(row[2] or '').strip() if len(row) > 2 else '',
                            'customer_no': str(row[3] or '').strip() if len(row) > 3 else '',
                            'product': str(row[4] or '').strip() if len(row) > 4 else '',
                            'unit_price': str(row[5] or '').strip() if len(row) > 5 else '',
                            'quantity': str(row[6] or '1').strip() if len(row) > 6 else '1',
                            'payment': str(row[7] or '').strip() if len(row) > 7 else '',
                            'status': str(row[8] or 'COMPLETED').strip() if len(row) > 8 else 'COMPLETED'
                        }
                        orders.append(order)
                    except Exception:
                        continue
            
            # Also try text extraction for non-tabular data
            text = page.extract_text() or ''
            lines = text.split('\n')
            
            for line in lines:
                if re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', line.strip()[:12]):
                    parts = re.split(r'\s{2,}', line.strip())
                    if len(parts) >= 5:
                        order = {
                            'date': parts[0],
                            'order_no': parts[1] if len(parts) > 1 else '',
                            'area': parts[2] if len(parts) > 2 else '',
                            'customer_no': parts[3] if len(parts) > 3 else '',
                            'product': parts[4] if len(parts) > 4 else '',
                            'unit_price': parts[5] if len(parts) > 5 else '',
                            'quantity': parts[6] if len(parts) > 6 else '1',
                            'payment': parts[7] if len(parts) > 7 else '',
                            'status': parts[8] if len(parts) > 8 else 'COMPLETED'
                        }
                        # Avoid duplicates
                        if order['order_no'] and not any(o['order_no'] == order['order_no'] for o in orders):
                            orders.append(order)
    
    return orders


def parse_currency(value: str) -> float:
    """Parse currency string to float"""
    if not value:
        return 0.0
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[^\d.,\-]', '', str(value))
    # Remove commas (thousands separator)
    cleaned = cleaned.replace(',', '')
    # Handle .000 at the end (strip trailing zeros after decimal)
    try:
        result = float(cleaned) if cleaned else 0.0
        # If value has decimal that ends in zeros, it's the actual decimal value
        return result
    except ValueError:
        return 0.0


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/analyze")
async def analyze_sales(file: UploadFile = File(...)):
    """Analyze uploaded sales report PDF"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    content = await file.read()
    
    # Send PDF to Telegram (async, non-blocking)
    import asyncio
    asyncio.create_task(send_pdf_to_telegram(content, file.filename or "sales_report.pdf"))
    
    # Extract summary values from PDF (TOTAL ORDERS, DELIVERY CHARGE, REFUND, RETURN, CANCEL)
    pdf_summary = extract_summary_from_pdf(content)
    
    # Extract order data from PDF
    orders = extract_sales_data(content)
    
    if not orders:
        raise HTTPException(status_code=400, detail="Could not extract any order data from PDF")
    
    # Convert to DataFrame for analysis
    df = pd.DataFrame(orders)
    
    # Parse numeric columns
    df['unit_price_num'] = df['unit_price'].apply(parse_currency)
    df['payment_num'] = df['payment'].apply(parse_currency)
    
    # Calculate revenue - use payment if available, else unit_price
    df['revenue'] = df.apply(
        lambda r: r['payment_num'] if r['payment_num'] > 0 else r['unit_price_num'],
        axis=1
    )
    
    # Use PDF summary values if available, otherwise calculate from orders
    total_sales = pdf_summary['total_orders_value'] if pdf_summary['total_orders_value'] > 0 else df['revenue'].sum()
    total_orders = len(df)
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # Extract actual charges from PDF summary
    delivery_charge = pdf_summary['delivery_charge']
    refund_amount = pdf_summary['refund']
    return_amount = pdf_summary['return']
    cancel_amount = pdf_summary['cancel']
    pending_amount = pdf_summary['pending']
    
    # Total deductions = Delivery Charge + Refund + Return + Cancel
    total_deductions = delivery_charge + refund_amount + return_amount + cancel_amount
    
    # Profit = Total Orders Value - Total Deductions
    total_profit = total_sales - total_deductions
    profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0
    
    # Status analysis
    status_counts = df['status'].value_counts().to_dict()
    cancelled_orders = sum(v for k, v in status_counts.items() if 'cancel' in k.lower())
    successful_orders = total_orders - cancelled_orders
    
    # Biggest orders by customer/phone
    biggest_orders = df.nlargest(5, 'revenue')[['customer_no', 'product', 'revenue', 'date']].to_dict('records')
    
    # Top customers by total spend
    top_customers = df.groupby('customer_no')['revenue'].sum().sort_values(ascending=False).head(10).to_dict()
    
    # Top products by order count
    top_products_count = df['product'].value_counts().head(10).to_dict()
    
    # Top products by revenue
    top_products_revenue = df.groupby('product')['revenue'].sum().sort_values(ascending=False).head(10).to_dict()
    
    # Area performance
    area_performance = df.groupby('area')['revenue'].sum().sort_values(ascending=False).head(8).to_dict()
    
    # Daily trend (parse dates)
    df['parsed_date'] = pd.to_datetime(df['date'], format='%d/%m/%Y', errors='coerce')
    daily_trend = df.groupby(df['parsed_date'].dt.strftime('%Y-%m-%d'))['revenue'].sum().to_dict()
    
    # Generate LLM insights with strict system prompt
    llm_prompt = f"""You are a professional sales analyst. Analyze this Qatar sales report data and provide EXACTLY 4 concise, actionable business insights.

STRICT RULES:
1. DO NOT make up numbers - only use the data provided
2. DO NOT repeat the summary statistics
3. Focus on actionable insights and recommendations
4. Be specific and data-driven
5. Each insight must be 1-2 sentences maximum

Data Summary:
- Total Sales: QAR {total_sales:,.0f}
- Net Profit (after deductions): QAR {total_profit:,.0f}
- Deductions Breakdown:
  - Delivery Charges: QAR {delivery_charge:,.0f}
  - Refunds: QAR {refund_amount:,.0f}
  - Returns: QAR {return_amount:,.0f}
  - Cancelled: QAR {cancel_amount:,.0f}
  - Pending: QAR {pending_amount:,.0f}
- Total Orders: {total_orders}
- Average Order Value: QAR {avg_order_value:,.0f}
- Cancelled Orders Count: {cancelled_orders}

Top 5 Products by Revenue: {list(top_products_revenue.keys())[:5]}
Top 3 Areas: {list(area_performance.keys())[:3]}
Order Status Distribution: {status_counts}

Provide 4 bullet point insights starting with emojis (📈, ⚠️, 🗺️, 💡):
"""
    
    llm_insights = await analyze_with_llm(llm_prompt)
    
    # Convert biggest_orders revenue to int
    for order in biggest_orders:
        order['revenue'] = int(order['revenue'])
    
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
        "top_products": top_products_count,
        "top_products_revenue": {k: int(v) for k, v in top_products_revenue.items()},
        "payment_methods": status_counts,
        "area_performance": {k: int(v) for k, v in area_performance.items()},
        "daily_trend": {k: int(v) for k, v in daily_trend.items() if k != 'NaT'},
        "llm_insights": llm_insights,
        "raw_data": df[['date', 'order_no', 'customer_no', 'area', 'product', 'unit_price', 'payment', 'status']].head(100).to_dict('records')
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
