'use client'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const COLORS = ['#4f46e5', '#10b981', '#f59e0b']

export default function StatsPanel({ patients }) {
    const total = patients.length
    const byStatus = patients.reduce((acc, p) => { acc[p.status] = (acc[p.status] || 0) + 1; return acc }, {})
    const pieData = Object.entries(byStatus).map(([k, v]) => ({ name: k, value: v }))
    const ageBuckets = [{ bucket: '<30', v: patients.filter(p => p.age < 30).length }, { bucket: '30-50', v: patients.filter(p => p.age >= 30 && p.age <= 50).length }, { bucket: '>50', v: patients.filter(p => p.age > 50).length }]

    return (
        <div className="grid grid-cols-3 gap-4">
            <div className="bg-white p-4 rounded shadow">
                <h4 className="font-medium">Total patients</h4>
                <div className="text-3xl font-bold">{total}</div>
            </div>
            <div className="bg-white p-4 rounded shadow col-span-1">
                <h4 className="font-medium mb-2">Status distribution</h4>
                <div style={{ width: '100%', height: 180 }}>
                    <ResponsiveContainer>
                        <PieChart>
                            <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={60} fill="#8884d8">
                                {pieData.map((entry, idx) => (<Cell key={idx} fill={COLORS[idx % COLORS.length]} />))}
                            </Pie>
                        </PieChart>
                    </ResponsiveContainer>
                </div>
            </div>
            <div className="bg-white p-4 rounded shadow col-span-1">
                <h4 className="font-medium mb-2">Age buckets</h4>
                <div style={{ width: '100%', height: 180 }}>
                    <ResponsiveContainer>
                        <BarChart data={ageBuckets}>
                            <XAxis dataKey="bucket" />
                            <YAxis />
                            <Tooltip />
                            <Bar dataKey="v" />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    )
}