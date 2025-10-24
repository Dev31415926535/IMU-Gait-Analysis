# src/processors.py
import numpy as np
from scipy.signal import find_peaks

def gyro_norm(gyro):
    g = np.array([gyro['Gx'], gyro['Gy'], gyro['Gz']], dtype=float)
    return np.linalg.norm(g)

def process_packet_accel_angle(packet):
    """
    Fallback simple accel-vector knee angle:
    Angle between IMU1 accel vector and IMU2 accel vector (degrees).
    Use when calibration not done or axes/positions unknown.
    """
    a1 = np.array([packet['IMU1']['Ax'], packet['IMU1']['Ay'], packet['IMU1']['Az']], dtype=float)
    a2 = np.array([packet['IMU2']['Ax'], packet['IMU2']['Ay'], packet['IMU2']['Az']], dtype=float)
    n1 = np.linalg.norm(a1)
    n2 = np.linalg.norm(a2)
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    dot = np.dot(a1, a2) / (n1 * n2)
    dot = float(max(-1.0, min(1.0, dot)))
    angle_rad = np.arccos(dot)
    return float(np.degrees(angle_rad))

def compute_stream_metrics(packets, sampling_rate=10.0, step_height_factor=0.6, min_step_s=0.25):
    """
    packets: list of dicts (each packet JSON from ESP)
    returns dict with times, angles, gyro_norms, step_times, cadence, etc.
    """
    N = len(packets)
    times = np.arange(N) / sampling_rate
    angles = []
    gnorms = []
    for p in packets:
        angle = process_packet_accel_angle(p)
        gnorm = gyro_norm(p['IMU2'])
        angles.append(angle)
        gnorms.append(gnorm)
    gnorms = np.array(gnorms)
    # step detection: peaks above mean + k*std, min distance
    if N == 0:
        return {}
    th = np.mean(gnorms) + step_height_factor * np.std(gnorms)
    min_dist_samples = max(1, int(min_step_s * sampling_rate))
    peaks, props = find_peaks(gnorms, height=th, distance=min_dist_samples)
    step_times = (peaks / sampling_rate).tolist()

    results = {
        'times': times.tolist(),
        'angles': angles,
        'gyro_norms': gnorms.tolist(),
        'step_times': step_times,
        'detected_steps': int(len(peaks)),
    }
    if len(step_times) >= 2:
        intervals = np.diff(step_times)
        mean_step_time = float(np.mean(intervals))
        results['mean_step_time_s'] = mean_step_time
        results['cadence_spm'] = 60.0 / mean_step_time if mean_step_time > 0 else None
    else:
        results['mean_step_time_s'] = None
        results['cadence_spm'] = None

    results['mean_knee_angle_deg'] = float(np.nanmean([a for a in angles if a is not None]))
    results['std_knee_angle_deg'] = float(np.nanstd([a for a in angles if a is not None]))
    results['peak_knee_angle_deg'] = float(np.nanmax([a for a in angles if a is not None]))
    return results



# # src/processors.py
# import numpy as np
# from scipy.signal import find_peaks
# from event_detector import detect_events_shank
# from spatial import stride_length_inverted_pendulum, stride_length_from_step_lengths, speed_from_stride
# from metrics import gait_summary


# # inside file, add:
# def compute_advanced_metrics(packets, sampling_rate=50.0, leg_length_m=0.95):
#     """
#     Higher-level metrics using shank packets (IMU2) and computed angles.
#     packets: original packets list from ESP (each packet has IMU1 and IMU2)
#     sampling_rate: fs used to convert indices -> time
#     leg_length_m: effective leg length (m) for inverted-pendulum
#     Returns dict with events, stride/step lengths and summary.
#     """
#     # extract shank packets list (IMU2) and angle series
#     shank_packets = [p['IMU2'] for p in packets]
#     # angles as fallback accel-angle
#     angles = [process_packet_accel_angle(p) for p in packets]

#     peaks, to_idx, hs_idx, proc_gyro = detect_events_shank(shank_packets, fs=sampling_rate)
#     # convert indices to timestamps
#     step_times = [i / sampling_rate for i in peaks]  # mid-swing times (approx)
#     hs_times = [i / sampling_rate for i in hs_idx]
#     to_times = [i / sampling_rate for i in to_idx]

#     # derive stride times assuming hs_times are same-foot HS (if alternating, user can adjust)
#     # Heuristic: if diffs of hs_times ~0.5 => alternating; if ~1.0 => same-foot
#     # For now assume hs_times are alternating -> compute stride_time from hs_times[::2]
#     # Simpler: compute step_times diffs and cadence
#     results = {}
#     results['peaks_idx'] = peaks
#     results['hs_idx'] = hs_idx
#     results['to_idx'] = to_idx
#     results['hs_times'] = hs_times
#     results['to_times'] = to_times
#     results['processed_gyro'] = proc_gyro.tolist()
#     # compute stride/step timing
#     if len(hs_times) >= 3:
#         step_intervals = np.diff(hs_times)
#         results['mean_step_time_s'] = float(np.mean(step_intervals))
#         results['cadence_spm'] = 60.0 / results['mean_step_time_s'] if results['mean_step_time_s']>0 else None
#     else:
#         results['mean_step_time_s'] = None
#         results['cadence_spm'] = None

#     # compute pitch at HS using a simple accel-based pitch from IMU2 as fallback:
#     # pitch = asin(Ay / |A|) (this is approximate; recommend orientation fusion)
#     acc_mag = np.array([[p['Ax'],p['Ay'],p['Az']] for p in shank_packets], dtype=float)
#     acc_norm = np.linalg.norm(acc_mag, axis=1)
#     # avoid divide by zero
#     acc_norm[acc_norm==0] = 1.0
#     pitch_est = np.arcsin(np.clip(acc_mag[:,1] / acc_norm, -1.0, 1.0))  # approximate pitch (rad)
#     # map pitch at hs_indices
#     pitch_at_hs = pitch_est[hs_idx] if len(hs_idx)>0 and len(pitch_est)>max(hs_idx) else pitch_est[::max(1,int(len(pitch_est)/max(1,len(hs_idx))))]
#     # compute stride lengths using inverted pendulum on HS of same foot (assumes hs_idx refers to same foot sequence)
#     stride_lengths = stride_length_inverted_pendulum(pitch_at_hs, leg_length_m)
#     results['stride_lengths_m'] = stride_lengths.tolist()
#     # approximate stride_times using alternate HS (two-step) if available
#     if len(hs_times) >= 3:
#         stride_times = np.array(hs_times[2:]) - np.array(hs_times[:-2])
#         results['stride_times_s'] = stride_times.tolist()
#     else:
#         results['stride_times_s'] = []

#     if len(results.get('stride_lengths_m', [])) and len(results.get('stride_times_s', [])):
#         speeds = speed_from_stride(results['stride_lengths_m'], results['stride_times_s'])
#         results['speeds_mps'] = speeds.tolist()
#     else:
#         results['speeds_mps'] = []

#     # knee peaks per stride (using angles)
#     knee_peaks = []
#     for i in range(len(hs_idx)-1):
#         s = hs_idx[i]
#         e = hs_idx[i+1]
#         if e > s and e <= len(angles):
#             seg = [a for a in angles[s:e+1] if a is not None]
#             if seg:
#                 knee_peaks.append(float(np.nanmax(seg)))
#     results['knee_peak_deg'] = knee_peaks

#     # gait summary
#     summary = gait_summary(results.get('stride_times_s', []), results.get('stride_lengths_m', []), knee_peaks)
#     results['summary'] = summary
#     return results


# def gyro_norm(gyro):
#     g = np.array([gyro['Gx'], gyro['Gy'], gyro['Gz']], dtype=float)
#     return np.linalg.norm(g)

# def process_packet_accel_angle(packet):
#     """
#     Fallback simple accel-vector knee angle:
#     Angle between IMU1 accel vector and IMU2 accel vector (degrees).
#     Use when calibration not done or axes/positions unknown.
#     """
#     a1 = np.array([packet['IMU1']['Ax'], packet['IMU1']['Ay'], packet['IMU1']['Az']], dtype=float)
#     a2 = np.array([packet['IMU2']['Ax'], packet['IMU2']['Ay'], packet['IMU2']['Az']], dtype=float)
#     n1 = np.linalg.norm(a1)
#     n2 = np.linalg.norm(a2)
#     if n1 < 1e-9 or n2 < 1e-9:
#         return None
#     dot = np.dot(a1, a2) / (n1 * n2)
#     dot = float(max(-1.0, min(1.0, dot)))
#     angle_rad = np.arccos(dot)
#     return float(np.degrees(angle_rad))

# def compute_stream_metrics(packets, sampling_rate=10.0, step_height_factor=0.6, min_step_s=0.25):
#     """
#     packets: list of dicts (each packet JSON from ESP)
#     returns dict with times, angles, gyro_norms, step_times, cadence, etc.
#     """
#     N = len(packets)
#     times = np.arange(N) / sampling_rate
#     angles = []
#     gnorms = []
#     for p in packets:
#         angle = process_packet_accel_angle(p)
#         gnorm = gyro_norm(p['IMU2'])
#         angles.append(angle)
#         gnorms.append(gnorm)
#     gnorms = np.array(gnorms)
#     # step detection: peaks above mean + k*std, min distance
#     if N == 0:
#         return {}
#     th = np.mean(gnorms) + step_height_factor * np.std(gnorms)
#     min_dist_samples = max(1, int(min_step_s * sampling_rate))
#     peaks, props = find_peaks(gnorms, height=th, distance=min_dist_samples)
#     step_times = (peaks / sampling_rate).tolist()

#     results = {
#         'times': times.tolist(),
#         'angles': angles,
#         'gyro_norms': gnorms.tolist(),
#         'step_times': step_times,
#         'detected_steps': int(len(peaks)),
#     }
#     if len(step_times) >= 2:
#         intervals = np.diff(step_times)
#         mean_step_time = float(np.mean(intervals))
#         results['mean_step_time_s'] = mean_step_time
#         results['cadence_spm'] = 60.0 / mean_step_time if mean_step_time > 0 else None
#     else:
#         results['mean_step_time_s'] = None
#         results['cadence_spm'] = None

#     results['mean_knee_angle_deg'] = float(np.nanmean([a for a in angles if a is not None]))
#     results['std_knee_angle_deg'] = float(np.nanstd([a for a in angles if a is not None]))
#     results['peak_knee_angle_deg'] = float(np.nanmax([a for a in angles if a is not None]))
#     return results
