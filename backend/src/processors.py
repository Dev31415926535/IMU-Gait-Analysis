
# # src/processors.py
# import numpy as np
# from scipy.signal import find_peaks
# from scipy.signal import medfilt

# def gyro_norm(gyro):
#     g = np.array([gyro['Gx'], gyro['Gy'], gyro['Gz']], dtype=float)
#     return np.linalg.norm(g)

# def process_packet_accel_angle(packet):
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

# def _mad(x):
#     med = np.median(x)
#     return np.median(np.abs(x - med))

# def compute_stream_metrics(packets, sampling_rate=10.0, step_height_factor=0.6, min_step_s=0.25):
#     N = len(packets)
#     times = np.arange(N) / sampling_rate
#     angles = []
#     gnorms = []
#     for p in packets:
#         angles.append(process_packet_accel_angle(p))
#         gnorms.append(gyro_norm(p['IMU2']))
#     gnorms = np.array(gnorms)

#     if N == 0:
#         return {}

#     # smooth gyro norms with small median filter to suppress spikes
#     k = 5
#     if N >= k:
#         # medfilt requires odd kernel
#         kernel = k if k % 2 == 1 else k+1
#         gnorms_s = medfilt(gnorms, kernel_size=kernel)
#     else:
#         gnorms_s = gnorms.copy()

#     # robust threshold: median + factor * MAD
#     med = float(np.median(gnorms_s))
#     mad = float(_mad(gnorms_s)) + 1e-12
#     th = med + step_height_factor * (mad * 1.4826)  # approx std from MAD

#     min_dist_samples = max(1, int(min_step_s * sampling_rate))
#     peaks, props = find_peaks(gnorms_s, height=th, distance=min_dist_samples)
#     step_times = (peaks / sampling_rate).tolist()

#     results = {
#         'times': times.tolist(),
#         'angles': angles,
#         'gyro_norms': gnorms.tolist(),
#         'gyro_norms_smooth': gnorms_s.tolist(),
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

#     valid_angles = [a for a in angles if a is not None]
#     results['mean_knee_angle_deg'] = float(np.nanmean(valid_angles)) if len(valid_angles) > 0 else None
#     results['std_knee_angle_deg'] = float(np.nanstd(valid_angles)) if len(valid_angles) > 0 else None
#     results['peak_knee_angle_deg'] = float(np.nanmax(valid_angles)) if len(valid_angles) > 0 else None
#     return results






"""
processors.py

Provides:
 - process_packet_accel_angle(packet): compute accel-based knee angle (deg) and gyro norm
 - compute_stream_metrics(packets, sampling_rate=..., ...): improved step detection & cadence

Designed to be a drop-in replacement for the project's processors module.
"""

from typing import Dict, Any, Tuple, List
import numpy as np
from scipy.signal import find_peaks, medfilt, butter, filtfilt

__all__ = ["process_packet_accel_angle", "compute_stream_metrics"]


def _mad(x: np.ndarray) -> float:
    """Return median absolute deviation (robust)."""
    med = np.median(x)
    return float(np.median(np.abs(x - med)))


def process_packet_accel_angle(packet: Dict[str, Any]) -> Tuple[float, float]:
    """
    Compute a simple accelerometer-based knee-angle surrogate (degrees) and gyro norm
    from a single packet.

    packet: expected to contain:
      packet['IMU1']['Ax/Ay/Az'] and packet['IMU2']['Ax/Ay/Az']
      packet['IMU2']['Gx/Gy/Gz'] (gyro used to compute norm)

    Returns:
      (angle_deg, gyro_norm)
      angle_deg is float (NaN if not computable)
      gyro_norm is float (0.0 if not available)
    """
    angle = float("nan")
    gnorm = 0.0
    try:
        a1 = np.array([packet["IMU1"]["Ax"], packet["IMU1"]["Ay"], packet["IMU1"]["Az"]], dtype=float)
        a2 = np.array([packet["IMU2"]["Ax"], packet["IMU2"]["Ay"], packet["IMU2"]["Az"]], dtype=float)
        n1 = np.linalg.norm(a1)
        n2 = np.linalg.norm(a2)
        if n1 > 1e-9 and n2 > 1e-9:
            dot = np.dot(a1, a2) / (n1 * n2)
            dot = float(max(-1.0, min(1.0, dot)))
            angle = float(np.degrees(np.arccos(dot)))
        else:
            angle = float("nan")
    except Exception:
        angle = float("nan")

    try:
        g = np.array([packet["IMU2"]["Gx"], packet["IMU2"]["Gy"], packet["IMU2"]["Gz"]], dtype=float)
        gnorm = float(np.linalg.norm(g))
    except Exception:
        gnorm = 0.0

    return angle, gnorm


def compute_stream_metrics(
    packets: List[Dict[str, Any]],
    sampling_rate: float = 50.0,
    # step detection tuning
    step_height_factor: float = 0.6,
    min_step_s: float = 0.25,
    bandpass_low_hz: float = 0.5,
    bandpass_high_hz: float = 3.0,
    min_angle_excursion_deg: float = 8.0,
    combine_gyro_weight: float = 0.25,
    peak_prominence_deg: float = 6.0,
) -> Dict[str, Any]:
    """
    Improved step detection:
      - compute knee-angle surrogate using accelerometer vectors from IMU1 & IMU2
      - smooth angle series with median filter
      - compute angular velocity (deg/s)
      - bandpass-filter angular velocity to physiological step band (default 0.5-3 Hz)
      - form activity signal = |bandpassed_ang_vel| optionally combined with smoothed gyro norm
      - dynamic thresholding using median + factor*MAD
      - peak detection using height, distance, and prominence
      - validate peaks by checking angle excursion around peak (prevents stillness false positives)
      - compute cadence (steps per minute) from validated peaks
    """
    N = len(packets)
    if N == 0:
        return {}

    # times array
    times = np.arange(N, dtype=float) / sampling_rate

    # extract angle (accelerometer-based surrogate) and gyro norms using helper
    angles = []
    gnorms = []
    for p in packets:
        ang, g = process_packet_accel_angle(p)
        angles.append(ang)
        gnorms.append(g)

    angles_arr = np.array(angles, dtype=float)
    gnorms = np.array(gnorms, dtype=float)

    # 1) Smooth angle series (median filter) to suppress spikes
    k = 5
    if N >= k:
        kernel = k if k % 2 == 1 else k + 1
        med_angle = float(np.nanmedian(angles_arr)) if np.isfinite(np.nanmedian(angles_arr)) else 0.0
        angles_filled = np.where(np.isfinite(angles_arr), angles_arr, med_angle)
        angles_s = medfilt(angles_filled, kernel_size=kernel)
    else:
        med_angle = float(np.nanmedian(angles_arr)) if np.isfinite(np.nanmedian(angles_arr)) else 0.0
        angles_s = np.where(np.isfinite(angles_arr), angles_arr, med_angle)

    # 2) Compute angular velocity (deg/s) via numeric gradient
    ang_vel = np.gradient(angles_s, 1.0 / sampling_rate)

    # 3) Bandpass filter angular velocity in step band
    nyq = 0.5 * sampling_rate
    low = max(0.0, bandpass_low_hz / nyq)
    high = min(0.999, bandpass_high_hz / nyq)
    if low >= high:
        ang_vel_bp = ang_vel.copy()
    else:
        try:
            b, a = butter(N=3, Wn=[low, high], btype="band")
            ang_vel_bp = filtfilt(b, a, ang_vel)
        except Exception:
            ang_vel_bp = ang_vel.copy()

    # 4) Build activity signal: absolute of bandpassed ang vel, optionally combined with smooth gyro-norm
    act = np.abs(ang_vel_bp)

    # smooth gyro-norm a bit
    gnorms_s = gnorms.copy()
    if N >= 5:
        kernel = 5 if 5 % 2 == 1 else 5 + 1
        gnorms_s = medfilt(gnorms_s, kernel_size=kernel)

    def _norm0to1(x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return x
        mn = float(np.nanmin(x))
        mx = float(np.nanmax(x))
        if mx - mn < 1e-9:
            return np.zeros_like(x)
        return (x - mn) / (mx - mn)

    act_n = _norm0to1(act)
    g_n = _norm0to1(gnorms_s)
    activity_signal = (1.0 - combine_gyro_weight) * act_n + combine_gyro_weight * g_n
    # scale activity_signal to reflect magnitude of act (so thresholding in deg/s makes sense)
    scale = float(np.nanmax(act)) if np.nanmax(act) > 0 else 1.0
    activity_signal = activity_signal * scale

    # 5) Dynamic threshold (median + factor * MAD)
    med_act = float(np.median(activity_signal))
    mad_act = _mad(activity_signal) + 1e-12
    threshold = med_act + step_height_factor * (mad_act * 1.4826)  # scaled MAD ~ std

    # 6) Peak detection
    min_dist_samples = max(1, int(min_step_s * sampling_rate))
    peaks, props = find_peaks(
        activity_signal,
        height=threshold,
        distance=min_dist_samples,
        prominence=peak_prominence_deg,
    )

    # 7) Validate peaks by checking angle excursion in a window around peak
    validated_peaks = []
    half_window_samples = max(1, int(0.4 * sampling_rate))  # check ~0.4s around peak (tunable)
    for p in peaks:
        lo = max(0, p - half_window_samples)
        hi = min(N - 1, p + half_window_samples)
        seg = angles_s[lo:hi + 1]
        if seg.size == 0:
            continue
        excursion = float(np.nanmax(seg) - np.nanmin(seg))
        if excursion >= min_angle_excursion_deg:
            validated_peaks.append(int(p))

    # 8) Convert to times and compute cadence
    step_times = (np.array(validated_peaks, dtype=float) / sampling_rate).tolist()
    detected_steps = int(len(validated_peaks))

    mean_step_time = None
    cadence_spm = None
    if len(validated_peaks) >= 2:
        intervals = np.diff(np.array(validated_peaks, dtype=float)) / sampling_rate
        # remove unreasonable intervals
        intervals = intervals[(intervals > 0) & (intervals < 5.0)]
        if intervals.size > 0:
            mean_step_time = float(np.mean(intervals))
            cadence_spm = 60.0 / mean_step_time if mean_step_time > 0 else None

    valid_angles = angles_arr[np.isfinite(angles_arr)]
    results = {
        "times": times.tolist(),
        "angles": [None if not np.isfinite(a) else float(a) for a in angles_arr.tolist()],
        "gyro_norms": gnorms.tolist(),
        "gyro_norms_smooth": gnorms_s.tolist(),
        "activity_signal": activity_signal.tolist(),
        "step_times": step_times,
        "detected_steps": detected_steps,
        "mean_step_time_s": mean_step_time,
        "cadence_spm": cadence_spm,
        "mean_knee_angle_deg": float(np.nanmean(valid_angles)) if valid_angles.size else None,
        "std_knee_angle_deg": float(np.nanstd(valid_angles)) if valid_angles.size else None,
        "peak_knee_angle_deg": float(np.nanmax(valid_angles)) if valid_angles.size else None,
    }
    return results
