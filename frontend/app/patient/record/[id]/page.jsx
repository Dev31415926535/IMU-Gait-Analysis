import Sidebar from '@/app/components/Sidebar'
import AngleChart from '@/app/components/AngleChart'
import { fetchRecording } from '@/lib/api'
import WebsocketAngleFeed from '@/app/components/WebsocketAngleFeed'

export default async function RecordPage({ params }) {
    const { id } = params
    let recording = null
    try { recording = await fetchRecording(id) } catch (e) { recording = { times: [0, 0.1, 0.2, 0.3, 0.4], angles: [45, 50, 62, 58, 48], metrics: { mean_knee_angle_deg: 52 } } }
    const chartData = recording.times.map((t, i) => ({ time_s: t, angle_deg: recording.angles?.[i] ?? null }))

    return (
        <Sidebar>
            <div className="space-y-4">
                <h2 className="text-2xl font-semibold">Recording {id}</h2>
                <AngleChart data={chartData} />
                <div>
                    <h4 className="font-medium mb-2">Live feed</h4>
                    {/* If you want to test live, use id 'live' or provide WebSocket URL in env as NEXT_PUBLIC_WS_URL */}
                    <WebsocketAngleFeed recordingId={id} />
                </div>
            </div>
        </Sidebar>
    )
}
