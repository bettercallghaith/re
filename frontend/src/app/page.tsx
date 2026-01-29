'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import {
    BarChart, Bar, PieChart, Pie, Cell, LineChart, Line,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

const CHART_COLORS = [
    '#10b981', '#6366f1', '#f59e0b', '#ec4899',
    '#8b5cf6', '#06b6d4', '#84cc16', '#f97316'
]

interface BiggestOrder {
    customer_no: string
    product: string
    revenue: number
    date: string
}

interface AnalysisData {
    summary: {
        total_sales: number
        total_profit: number
        total_charges: number
        profit_margin: number
        total_orders: number
        avg_order_value: number
        successful_orders: number
        cancelled_orders: number
        success_rate: number
    }
    biggest_orders: BiggestOrder[]
    top_customers: Record<string, number>
    top_products: Record<string, number>
    top_products_revenue: Record<string, number>
    payment_methods: Record<string, number>
    area_performance: Record<string, number>
    daily_trend: Record<string, number>
    llm_insights: string
    raw_data: Array<{
        date: string
        order_no: string
        customer_no: string
        area: string
        product: string
        unit_price: string
        payment: string
        status: string
    }>
}

function formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-QA', {
        style: 'decimal',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value)
}

function AnimatedNumber({ value, prefix = '', suffix = '' }: { value: number, prefix?: string, suffix?: string }) {
    const [displayValue, setDisplayValue] = useState(0)

    useEffect(() => {
        const duration = 1500
        const steps = 60
        const increment = value / steps
        let current = 0

        const timer = setInterval(() => {
            current += increment
            if (current >= value) {
                setDisplayValue(value)
                clearInterval(timer)
            } else {
                setDisplayValue(current)
            }
        }, duration / steps)

        return () => clearInterval(timer)
    }, [value])

    return <>{prefix}{formatCurrency(displayValue)}{suffix}</>
}

function CustomTooltip({ active, payload, label }: any) {
    if (!active || !payload || !payload.length) return null

    return (
        <div style={{
            background: '#fff',
            border: '1px solid #e5e5e5',
            borderRadius: '8px',
            padding: '12px 16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        }}>
            <p style={{ color: '#666', fontSize: '12px', marginBottom: '4px' }}>{label}</p>
            <p style={{ color: '#111', fontSize: '14px', fontWeight: 600 }}>
                {payload[0].name === 'revenue' ? 'QAR ' : ''}{formatCurrency(payload[0].value)}
            </p>
        </div>
    )
}

export default function Dashboard() {
    const [analysis, setAnalysis] = useState<AnalysisData | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [currentPage, setCurrentPage] = useState(1)
    const fileInputRef = useRef<HTMLInputElement>(null)
    const itemsPerPage = 10

    const handleUpload = useCallback(async (file: File) => {
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            setError('Please upload a PDF file')
            return
        }

        setLoading(true)
        setError(null)

        const formData = new FormData()
        formData.append('file', file)

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                body: formData,
            })

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}))
                throw new Error(errorData.detail || 'Analysis failed')
            }

            const data = await response.json()
            setAnalysis(data)
            setCurrentPage(1)
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to analyze file')
        } finally {
            setLoading(false)
        }
    }, [])

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        const file = e.dataTransfer.files[0]
        if (file) handleUpload(file)
    }, [handleUpload])

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(true)
    }, [])

    const handleDragLeave = useCallback(() => {
        setIsDragging(false)
    }, [])

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) handleUpload(file)
    }, [handleUpload])

    const topProductsData = analysis
        ? Object.entries(analysis.top_products).slice(0, 8).map(([name, value]) => ({
            name: name.length > 20 ? name.slice(0, 17) + '...' : name,
            orders: value,
        }))
        : []

    const areaData = analysis
        ? Object.entries(analysis.area_performance).map(([name, value]) => ({
            name: name.length > 15 ? name.slice(0, 12) + '...' : name,
            revenue: value,
        }))
        : []

    const paymentData = analysis
        ? Object.entries(analysis.payment_methods).map(([name, value]) => ({
            name,
            value,
        }))
        : []

    const dailyTrendData = analysis
        ? Object.entries(analysis.daily_trend)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([date, value]) => ({
                date: date.slice(5),
                revenue: value,
            }))
        : []

    const topCustomersData = analysis
        ? Object.entries(analysis.top_customers).slice(0, 8).map(([phone, revenue]) => ({
            phone: phone.length > 12 ? phone.slice(-8) : phone,
            revenue,
        }))
        : []

    const paginatedData = analysis?.raw_data?.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    ) || []

    const totalPages = Math.ceil((analysis?.raw_data?.length || 0) / itemsPerPage)

    const getStatusClass = (status: string) => {
        const s = status.toLowerCase()
        if (s.includes('cancel')) return 'cancelled'
        if (s.includes('cash') || s.includes('online') || s.includes('complete')) return 'success'
        return 'pending'
    }

    return (
        <main className="container">
            <header className="header">
                <div className="header-info">
                    <h1 className="title">Sales Analytics</h1>
                    <p className="subtitle">Upload your sales report PDF for AI-powered insights</p>
                </div>
                {analysis && (
                    <div className="header-actions">
                        <button className="btn btn-secondary" onClick={() => setAnalysis(null)}>
                            ↺ New Report
                        </button>
                    </div>
                )}
            </header>

            {!analysis && !loading && (
                <div
                    className={`upload-area ${isDragging ? 'dragging' : ''}`}
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf"
                        onChange={handleFileSelect}
                        style={{ display: 'none' }}
                    />
                    <svg className="upload-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="upload-text">
                        <strong>Click to upload</strong> or drag and drop
                    </p>
                    <p className="upload-hint">PDF sales reports only</p>
                </div>
            )}

            {error && (
                <div style={{
                    background: 'rgba(239, 68, 68, 0.05)',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                    borderRadius: '12px',
                    padding: '16px',
                    marginBottom: '24px',
                    color: '#dc2626',
                    fontSize: '14px',
                }}>
                    {error}
                </div>
            )}

            {loading && (
                <div className="loading-container">
                    <div className="spinner" />
                    <p className="loading-text">Analyzing your sales data...</p>
                </div>
            )}

            {analysis && !loading && (
                <>
                    {/* Stats Grid - 6 columns */}
                    <div className="stats-grid">
                        <div className="card stat-card animate-in delay-1">
                            <span className="stat-label">Total Sales</span>
                            <span className="stat-value">
                                <AnimatedNumber value={analysis.summary.total_sales} prefix="QAR " />
                            </span>
                        </div>
                        <div className="card stat-card animate-in delay-2">
                            <span className="stat-label">Profit</span>
                            <span className="stat-value profit">
                                <AnimatedNumber value={analysis.summary.total_profit} prefix="QAR " />
                            </span>
                            <span className="stat-change positive">{analysis.summary.profit_margin}% margin</span>
                        </div>
                        <div className="card stat-card animate-in delay-3">
                            <span className="stat-label">Charges</span>
                            <span className="stat-value charges">
                                <AnimatedNumber value={analysis.summary.total_charges} prefix="QAR " />
                            </span>
                        </div>
                        <div className="card stat-card animate-in delay-4">
                            <span className="stat-label">Total Orders</span>
                            <span className="stat-value">
                                <AnimatedNumber value={analysis.summary.total_orders} />
                            </span>
                        </div>
                        <div className="card stat-card animate-in delay-5">
                            <span className="stat-label">Avg Order</span>
                            <span className="stat-value">
                                <AnimatedNumber value={analysis.summary.avg_order_value} prefix="QAR " />
                            </span>
                        </div>
                        <div className="card stat-card animate-in delay-6">
                            <span className="stat-label">Success Rate</span>
                            <span className="stat-value">
                                <AnimatedNumber value={analysis.summary.success_rate} suffix="%" />
                            </span>
                            {analysis.summary.cancelled_orders > 0 && (
                                <span className="stat-change negative">{analysis.summary.cancelled_orders} cancelled</span>
                            )}
                        </div>
                    </div>

                    {/* Biggest Orders by Phone */}
                    {analysis.biggest_orders && analysis.biggest_orders.length > 0 && (
                        <div className="biggest-orders animate-in">
                            <h3 className="section-title">🏆 Biggest Orders by Customer</h3>
                            <div className="order-cards">
                                {analysis.biggest_orders.map((order, idx) => (
                                    <div key={idx} className="order-card">
                                        <span className="order-card-phone">📱 {order.customer_no || 'Unknown'}</span>
                                        <span className="order-card-product">{order.product}</span>
                                        <span className="order-card-amount">QAR {formatCurrency(order.revenue)}</span>
                                        <span className="order-card-date">{order.date}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* AI Insights */}
                    {analysis.llm_insights && (
                        <div className="insights-panel animate-in">
                            <div className="insights-header">
                                <span className="insights-icon">✨</span>
                                <span className="insights-title">AI Insights</span>
                            </div>
                            <div className="insights-content">{analysis.llm_insights}</div>
                        </div>
                    )}

                    {/* Charts */}
                    <div className="charts-grid">
                        {/* Top Products */}
                        <div className="card animate-in">
                            <h3 className="card-title">Top Products by Orders</h3>
                            <ResponsiveContainer width="100%" height={280}>
                                <BarChart data={topProductsData} layout="vertical" margin={{ left: 10, right: 20 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                                    <XAxis type="number" stroke="#999" fontSize={11} />
                                    <YAxis dataKey="name" type="category" stroke="#999" fontSize={11} width={120} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Bar
                                        dataKey="orders"
                                        fill="#10b981"
                                        radius={[0, 4, 4, 0]}
                                        animationBegin={200}
                                        animationDuration={1200}
                                    >
                                        {topProductsData.map((_, index) => (
                                            <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Top Customers by Phone */}
                        <div className="card animate-in">
                            <h3 className="card-title">Top Customers by Revenue</h3>
                            <ResponsiveContainer width="100%" height={280}>
                                <BarChart data={topCustomersData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                                    <XAxis dataKey="phone" stroke="#999" fontSize={11} />
                                    <YAxis stroke="#999" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Bar
                                        dataKey="revenue"
                                        fill="#6366f1"
                                        radius={[4, 4, 0, 0]}
                                        animationBegin={400}
                                        animationDuration={1200}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Area Performance */}
                        <div className="card animate-in">
                            <h3 className="card-title">Revenue by Area</h3>
                            <ResponsiveContainer width="100%" height={280}>
                                <BarChart data={areaData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                                    <XAxis dataKey="name" stroke="#999" fontSize={11} />
                                    <YAxis stroke="#999" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Bar
                                        dataKey="revenue"
                                        fill="#f59e0b"
                                        radius={[4, 4, 0, 0]}
                                        animationBegin={600}
                                        animationDuration={1200}
                                    >
                                        {areaData.map((_, index) => (
                                            <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                        ))}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Payment Methods Pie */}
                        <div className="card animate-in">
                            <h3 className="card-title">Order Status Distribution</h3>
                            <ResponsiveContainer width="100%" height={280}>
                                <PieChart>
                                    <Pie
                                        data={paymentData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={100}
                                        paddingAngle={2}
                                        dataKey="value"
                                        animationBegin={800}
                                        animationDuration={1200}
                                    >
                                        {paymentData.map((_, index) => (
                                            <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend
                                        verticalAlign="bottom"
                                        height={36}
                                        formatter={(value) => <span style={{ color: '#666', fontSize: '12px' }}>{value}</span>}
                                    />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>

                        {/* Daily Trend */}
                        {dailyTrendData.length > 1 && (
                            <div className="card animate-in" style={{ gridColumn: 'span 2' }}>
                                <h3 className="card-title">Daily Revenue Trend</h3>
                                <ResponsiveContainer width="100%" height={280}>
                                    <LineChart data={dailyTrendData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                                        <XAxis dataKey="date" stroke="#999" fontSize={11} />
                                        <YAxis stroke="#999" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                                        <Tooltip content={<CustomTooltip />} />
                                        <Line
                                            type="monotone"
                                            dataKey="revenue"
                                            stroke="#10b981"
                                            strokeWidth={2}
                                            dot={{ fill: '#10b981', strokeWidth: 0, r: 4 }}
                                            activeDot={{ r: 6 }}
                                            animationBegin={1000}
                                            animationDuration={1500}
                                        />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        )}
                    </div>

                    {/* Orders Table */}
                    <div className="card animate-in">
                        <h3 className="card-title">Recent Orders</h3>
                        <div className="table-container">
                            <table className="table">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Order No</th>
                                        <th>Customer</th>
                                        <th>Area</th>
                                        <th>Product</th>
                                        <th>Price</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {paginatedData.map((order, idx) => (
                                        <tr key={idx}>
                                            <td>{order.date}</td>
                                            <td>{order.order_no}</td>
                                            <td>{order.customer_no}</td>
                                            <td>{order.area}</td>
                                            <td style={{ maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {order.product}
                                            </td>
                                            <td>{order.unit_price}</td>
                                            <td>
                                                <span className={`status ${getStatusClass(order.status)}`}>
                                                    {order.status}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        {totalPages > 1 && (
                            <div className="pagination">
                                <button
                                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                    disabled={currentPage === 1}
                                >
                                    ← Prev
                                </button>
                                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                                    let page = i + 1
                                    if (totalPages > 5) {
                                        if (currentPage > 3) page = currentPage - 2 + i
                                        if (currentPage > totalPages - 3) page = totalPages - 4 + i
                                    }
                                    return (
                                        <button
                                            key={page}
                                            className={currentPage === page ? 'active' : ''}
                                            onClick={() => setCurrentPage(page)}
                                        >
                                            {page}
                                        </button>
                                    )
                                })}
                                <button
                                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                    disabled={currentPage === totalPages}
                                >
                                    Next →
                                </button>
                            </div>
                        )}
                    </div>
                </>
            )}
        </main>
    )
}
