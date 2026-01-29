import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
    title: 'Sales Analytics Dashboard',
    description: 'AI-powered sales report analysis with beautiful visualizations',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="en">
            <body>{children}</body>
        </html>
    )
}
