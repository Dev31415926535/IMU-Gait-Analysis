'use client'
import { useEffect, useState, useRef } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

export default function WebsocketAngleFeed({ recordingId }) {
    const [points, setPoints] = useState([])
    const wsRef = useRef(null)
    useEffect(() => {
        const wsUrl = process.env.NEXT_PUBLIC_WS_URL || `ws://localhost:8000/ws` // replace with your WS
        let ws
        try {
            ws = new WebSocket(wsUrl)
        } catch (e) { console.error('WS init failed', e); return }
        wsRef.current = ws
        ws.onopen = () => console.log('ws open')
        ws.onmessage = (ev) => {
            try {
                const pkt = JSON.parse(ev.data)
                // Expecting { time_s: number, angle_deg: number, id: optional }
                if (pkt && (pkt.id === recordingId || recordingId === 'live')) {
                    setPoints(prev => {
                        const next = [...prev.slice(-299), { time_s: pkt.time_s ?? prev.length * 0.1, angle_deg: pkt.angle_deg }]
                        return next
                    })
                }
            } catch (e) { console.error('ws parse', e) }
        }
        ws.onerror = (e) => console.error('ws error', e)
        ws.onclose = () => console.log('ws closed')
        return () => ws && ws.close()
    }, [recordingId])

    return (
        <div className="bg-white p-4 rounded shadow">
            <div style={{ width: '100%', height: 300 }}>
                <ResponsiveContainer>
                    <LineChart data={points}>
                        <XAxis dataKey="time_s" tick={{ fontSize: 12 }} />
                        <YAxis domain={[0, 'dataMax + 10']} />
                        <Tooltip />
                        <Line type="monotone" dataKey="angle_deg" stroke="#4f46e5" strokeWidth={2} dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
            {points.length === 0 && <div className="text-gray-500 mt-2">No live data yet. Make sure your backend WS is running and emitting packets.</div>}
        </div>
    )
}