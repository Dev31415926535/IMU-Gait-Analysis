'use client'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

export default function AngleChart({ data }) {
    // data: [{time_s: number, angle_deg: number}, ...]
    return (
        <div className="bg-white p-4 rounded shadow">
            <h4 className="mb-2 font-medium">Knee Angle</h4>
            <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                    <LineChart data={data}>
                        <XAxis dataKey="time_s" tick={{ fontSize: 12 }} />
                        <YAxis domain={[0, 'dataMax + 10']} />
                        <Tooltip />
                        <Line type="monotone" dataKey="angle_deg" stroke="#4f46e5" strokeWidth={2} dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    )
}