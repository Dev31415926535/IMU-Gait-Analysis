"""
processors_enhanced.py

Enhanced gait analysis with additional metrics for single-leg IMU setup (thigh + shank).
Adds swing-stance detection, gait phase timing, and additional kinematic parameters.
"""

from typing import Dict, Any, Tuple, List, Optional
import numpy as np
from scipy.signal import find_peaks, medfilt, butter, filtfilt, hilbert
from scipy.interpolate import interp1d
import warnings
warnings.filterwarnings('ignore')

__all__ = ["process_packet_accel_angle", "compute_stream_metrics", "GaitPhaseDetector"]


class GaitPhaseDetector:
    """
    Detects gait phases (stance/swing) using IMU signals.
    Uses gyroscope patterns and knee angle changes for phase detection.
    """
    
    def __init__(self, sampling_rate: float = 50.0):
        self.fs = sampling_rate
        
    def detect_gait_events(
        self, 
        knee_angles: np.ndarray,
        shank_gyro: np.ndarray,
        thigh_gyro: np.ndarray,
        validated_steps: List[int]
    ) -> Dict[str, Any]:
        """
        Detect heel strikes and toe-offs to identify stance/swing phases.
        
        Gait cycle events:
        - Heel Strike (HS): Start of stance phase
        - Toe Off (TO): End of stance phase, start of swing phase
        
        Returns dict with detected events and phase durations.
        """
        N = len(knee_angles)
        
        # Smooth signals for event detection
        if N >= 5:
            knee_smooth = medfilt(knee_angles, kernel_size=5)
            shank_smooth = medfilt(shank_gyro, kernel_size=5)
        else:
            knee_smooth = knee_angles
            shank_smooth = shank_gyro
            
        # Detect heel strikes (HS) - typically occurs at local minima of shank angular velocity
        # during the transition from swing to stance
        hs_candidates = []
        to_candidates = []
        
        # For each detected step, find the gait events
        for i, step_idx in enumerate(validated_steps):
            # Define search window around step
            window_size = int(0.5 * self.fs)  # 0.5 second window
            start = max(0, step_idx - window_size)
            end = min(N, step_idx + window_size)
            
            # Find heel strike (negative peak in shank gyro before step)
            hs_search_start = max(0, step_idx - int(0.3 * self.fs))
            hs_search_end = step_idx
            if hs_search_end > hs_search_start:
                segment = shank_smooth[hs_search_start:hs_search_end]
                if len(segment) > 0:
                    local_min_idx = np.argmin(segment)
                    hs_idx = hs_search_start + local_min_idx
                    hs_candidates.append(hs_idx)
            
            # Find toe-off (positive peak in shank gyro after heel strike)
            if i < len(validated_steps) - 1:
                next_step = validated_steps[i + 1]
                to_search_start = step_idx
                to_search_end = min(next_step, step_idx + int(0.4 * self.fs))
                if to_search_end > to_search_start:
                    segment = shank_smooth[to_search_start:to_search_end]
                    if len(segment) > 0:
                        local_max_idx = np.argmax(segment)
                        to_idx = to_search_start + local_max_idx
                        to_candidates.append(to_idx)
        
        # Calculate phase durations
        stance_durations = []
        swing_durations = []
        gait_cycles = []
        
        # Match HS and TO events to create complete gait cycles
        for i in range(len(hs_candidates) - 1):
            hs1 = hs_candidates[i]
            hs2 = hs_candidates[i + 1]
            
            # Find TO between these two HS events
            to_between = [to for to in to_candidates if hs1 < to < hs2]
            if to_between:
                to = to_between[0]
                
                # Stance phase: HS to TO
                stance_duration = (to - hs1) / self.fs
                # Swing phase: TO to next HS
                swing_duration = (hs2 - to) / self.fs
                
                # Validate durations (typical ranges)
                if 0.2 < stance_duration < 1.5 and 0.1 < swing_duration < 1.0:
                    stance_durations.append(stance_duration)
                    swing_durations.append(swing_duration)
                    gait_cycles.append({
                        'hs_idx': hs1,
                        'to_idx': to,
                        'next_hs_idx': hs2,
                        'stance_duration': stance_duration,
                        'swing_duration': swing_duration,
                        'cycle_duration': stance_duration + swing_duration
                    })
        
        # Calculate metrics
        results = {
            'heel_strikes': hs_candidates,
            'toe_offs': to_candidates,
            'gait_cycles': gait_cycles,
            'stance_durations': stance_durations,
            'swing_durations': swing_durations
        }
        
        if stance_durations and swing_durations:
            results['mean_stance_time'] = float(np.mean(stance_durations))
            results['std_stance_time'] = float(np.std(stance_durations))
            results['mean_swing_time'] = float(np.mean(swing_durations))
            results['std_swing_time'] = float(np.std(swing_durations))
            results['swing_stance_ratio'] = results['mean_swing_time'] / results['mean_stance_time']
            
            # Stance percentage (typical: 60% stance, 40% swing in normal walking)
            mean_cycle = results['mean_stance_time'] + results['mean_swing_time']
            results['stance_percentage'] = (results['mean_stance_time'] / mean_cycle) * 100
            results['swing_percentage'] = (results['mean_swing_time'] / mean_cycle) * 100
        else:
            results['mean_stance_time'] = None
            results['mean_swing_time'] = None
            results['swing_stance_ratio'] = None
            results['stance_percentage'] = None
            results['swing_percentage'] = None
            
        return results


def _mad(x: np.ndarray) -> float:
    """Return median absolute deviation (robust)."""
    med = np.median(x)
    return float(np.median(np.abs(x - med)))


def calculate_joint_kinematics(packet: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculate additional kinematic parameters from IMU data.
    
    Returns:
    - Knee angular velocity
    - Thigh inclination angle
    - Shank inclination angle
    """
    results = {}
    
    try:
        # Thigh inclination (using IMU1 accelerometer)
        ax1 = packet["IMU1"]["Ax"]
        ay1 = packet["IMU1"]["Ay"]
        az1 = packet["IMU1"]["Az"]
        
        # Inclination relative to vertical (assuming z is vertical)
        thigh_inclination = np.degrees(np.arctan2(np.sqrt(ax1**2 + ay1**2), az1))
        results['thigh_inclination'] = float(thigh_inclination)
        
        # Shank inclination (using IMU2 accelerometer)
        ax2 = packet["IMU2"]["Ax"]
        ay2 = packet["IMU2"]["Ay"]
        az2 = packet["IMU2"]["Az"]
        
        shank_inclination = np.degrees(np.arctan2(np.sqrt(ax2**2 + ay2**2), az2))
        results['shank_inclination'] = float(shank_inclination)
        
        # Knee angular velocity (difference in gyro signals)
        gx1 = packet["IMU1"]["Gx"]
        gy1 = packet["IMU1"]["Gy"]
        gz1 = packet["IMU1"]["Gz"]
        
        gx2 = packet["IMU2"]["Gx"]
        gy2 = packet["IMU2"]["Gy"]
        gz2 = packet["IMU2"]["Gz"]
        
        # Relative angular velocity (simplified - assumes aligned sensors)
        knee_angular_velocity = np.sqrt((gx2-gx1)**2 + (gy2-gy1)**2 + (gz2-gz1)**2)
        results['knee_angular_velocity'] = float(knee_angular_velocity)
        
    except Exception:
        results['thigh_inclination'] = None
        results['shank_inclination'] = None
        results['knee_angular_velocity'] = None
    
    return results


def process_packet_accel_angle(packet: Dict[str, Any]) -> Tuple[float, float, Dict]:
    """
    Enhanced packet processing with additional kinematics.
    
    Returns:
      (angle_deg, gyro_norm, kinematics_dict)
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
    except Exception:
        angle = float("nan")

    try:
        g = np.array([packet["IMU2"]["Gx"], packet["IMU2"]["Gy"], packet["IMU2"]["Gz"]], dtype=float)
        gnorm = float(np.linalg.norm(g))
    except Exception:
        gnorm = 0.0
    
    # Calculate additional kinematics
    kinematics = calculate_joint_kinematics(packet)

    return angle, gnorm, kinematics


def estimate_step_asymmetry(step_times: List[float]) -> Optional[float]:
    """
    Estimate step time asymmetry (useful for detecting limping or pathological gait).
    Returns coefficient of variation of step intervals.
    """
    if len(step_times) < 3:
        return None
    
    intervals = np.diff(step_times)
    if len(intervals) < 2:
        return None
    
    mean_interval = np.mean(intervals)
    std_interval = np.std(intervals)
    
    if mean_interval > 0:
        cv = (std_interval / mean_interval) * 100  # Coefficient of variation in %
        return float(cv)
    return None


def compute_stream_metrics(
    packets: List[Dict[str, Any]],
    sampling_rate: float = 50.0,
    # step detection tuning
    step_height_factor: float = 0.6,
    min_step_s: float = 0.25,
    bandpass_low_hz: float = 0.5,
    bandpass_high_hz: float = 3.0,
    min_angle_excursion_deg: float = 20.0,
    combine_gyro_weight: float = 0.25,
    peak_prominence_deg: float = 6.0,
) -> Dict[str, Any]:
    """
    Enhanced gait metrics computation with swing-stance analysis.
    
    NOTE ON LIMITATIONS:
    - Step length CANNOT be accurately measured with only IMUs without position reference
    - Spatial parameters (distance, velocity) require additional sensors or fusion techniques
    - Single-leg setup limits bilateral comparison metrics
    """
    N = len(packets)
    if N == 0:
        return {}

    # times array
    times = np.arange(N, dtype=float) / sampling_rate

    # Extract angles, gyro norms, and additional kinematics
    angles = []
    gnorms = []
    thigh_gyros = []
    shank_gyros = []
    all_kinematics = []
    
    for p in packets:
        ang, g, kin = process_packet_accel_angle(p)
        angles.append(ang)
        gnorms.append(g)
        all_kinematics.append(kin)
        
        # Extract individual gyro components for phase detection
        try:
            thigh_gyro = np.linalg.norm([p["IMU1"]["Gx"], p["IMU1"]["Gy"], p["IMU1"]["Gz"]])
            shank_gyro = np.linalg.norm([p["IMU2"]["Gx"], p["IMU2"]["Gy"], p["IMU2"]["Gz"]])
            thigh_gyros.append(thigh_gyro)
            shank_gyros.append(shank_gyro)
        except:
            thigh_gyros.append(0.0)
            shank_gyros.append(0.0)
    if sum(angles)/len(angles)<90:
        angles_arr = np.array(angles, dtype=float)
    else:
        angles_arr = np.array([180-i for i in angles], dtype=float)
    
    gnorms = np.array(gnorms, dtype=float)
    thigh_gyros = np.array(thigh_gyros, dtype=float)
    shank_gyros = np.array(shank_gyros, dtype=float)

    # 1) Smooth angle series
    k = 5
    if N >= k:
        kernel = k if k % 2 == 1 else k + 1
        med_angle = float(np.nanmedian(angles_arr)) if np.isfinite(np.nanmedian(angles_arr)) else 0.0
        angles_filled = np.where(np.isfinite(angles_arr), angles_arr, med_angle)
        angles_s = medfilt(angles_filled, kernel_size=kernel)
    else:
        med_angle = float(np.nanmedian(angles_arr)) if np.isfinite(np.nanmedian(angles_arr)) else 0.0
        angles_s = np.where(np.isfinite(angles_arr), angles_arr, med_angle)

    # 2) Compute angular velocity
    ang_vel = np.gradient(angles_s, 1.0 / sampling_rate)

    # 3) Bandpass filter
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

    # 4) Build activity signal
    act = np.abs(ang_vel_bp)
    
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
    scale = float(np.nanmax(act)) if np.nanmax(act) > 0 else 1.0
    activity_signal = activity_signal * scale

    # 5) Dynamic threshold
    med_act = float(np.median(activity_signal))
    mad_act = _mad(activity_signal) + 1e-12
    threshold = med_act + step_height_factor * (mad_act * 1.4826)

    # 6) Peak detection
    min_dist_samples = max(1, int(min_step_s * sampling_rate))
    peaks, props = find_peaks(
        activity_signal,
        height=threshold,
        distance=min_dist_samples,
        prominence=peak_prominence_deg,
    )

    # 7) Validate peaks
    validated_peaks = []
    half_window_samples = max(1, int(0.4 * sampling_rate))
    for p in peaks:
        lo = max(0, p - half_window_samples)
        hi = min(N - 1, p + half_window_samples)
        seg = angles_s[lo:hi + 1]
        if seg.size == 0:
            continue
        excursion = float(np.nanmax(seg) - np.nanmin(seg))
        if excursion >= min_angle_excursion_deg:
            validated_peaks.append(int(p))

    # Convert to times
    step_times = (np.array(validated_peaks, dtype=float) / sampling_rate).tolist()
    detected_steps = int(len(validated_peaks))
    
    # Step timestamps with actual time values
    step_timestamps = [{'step_number': i+1, 'time_s': t} for i, t in enumerate(step_times)]

    # Basic cadence calculation
    mean_step_time = None
    cadence_spm = None
    if len(validated_peaks) >= 2:
        intervals = np.diff(np.array(validated_peaks, dtype=float)) / sampling_rate
        intervals = intervals[(intervals > 0) & (intervals < 5.0)]
        if intervals.size > 0:
            mean_step_time = float(np.mean(intervals))
            cadence_spm = 60.0 / mean_step_time if mean_step_time > 0 else None

    # Detect gait phases (swing/stance)
    phase_detector = GaitPhaseDetector(sampling_rate)
    phase_results = phase_detector.detect_gait_events(
        angles_s, shank_gyros, thigh_gyros, validated_peaks
    )

    # Calculate step asymmetry
    step_asymmetry = estimate_step_asymmetry(step_times)

    # Knee angle metrics
    valid_angles = angles_arr[np.isfinite(angles_arr)]
    
    # Range of motion during detected steps
    rom_values = []
    for p in validated_peaks:
        window = int(0.5 * sampling_rate)
        lo = max(0, p - window)
        hi = min(N - 1, p + window)
        seg = angles_s[lo:hi + 1]
        if seg.size > 0:
            rom = float(np.nanmax(seg) - np.nanmin(seg))
            rom_values.append(rom)
    
    mean_rom = float(np.mean(rom_values)) if rom_values else None
    
    # Compile results
    results = {
        # Time series data
        "times": times.tolist(),
        "angles": [None if not np.isfinite(a) else float(a) for a in angles_arr.tolist()],

        # Step detection
        "step_times": step_times,
        # "step_timestamps": step_timestamps,
        "detected_steps": detected_steps,
        
        # Temporal parameters
        "mean_step_time_s": mean_step_time,
        "cadence_spm": cadence_spm,
        "step_asymmetry_cv": step_asymmetry,
        
        # Swing-Stance parameters
        "mean_stance_time": phase_results.get('mean_stance_time'),
        "std_stance_time": phase_results.get('std_stance_time'),
        "mean_swing_time": phase_results.get('mean_swing_time'),
        "std_swing_time": phase_results.get('std_swing_time'),
        "swing_stance_ratio": phase_results.get('swing_stance_ratio'),
        "stance_percentage": phase_results.get('stance_percentage'),
        "swing_percentage": phase_results.get('swing_percentage'),
        
        # Kinematic parameters
        "mean_knee_angle_deg": float(np.nanmean(valid_angles)) if valid_angles.size else None,
        "std_knee_angle_deg": float(np.nanstd(valid_angles)) if valid_angles.size else None,
        "peak_knee_angle_deg": float(np.nanmax(valid_angles)) if valid_angles.size else None,
        "min_knee_angle_deg": float(np.nanmin(valid_angles)) if valid_angles.size else None,
        "knee_rom_deg": mean_rom,
        
        # Gait events (for debugging/visualization)
        "heel_strikes": [int(x) for x in phase_results.get('heel_strikes', [])],
        "toe_offs": [int(x) for x in phase_results.get('toe_offs', [])],
        "gait_cycles": [
            {
                'hs_idx': int(cycle['hs_idx']),
                'to_idx': int(cycle['to_idx']),
                'next_hs_idx': int(cycle['next_hs_idx']),
                'stance_duration': float(cycle['stance_duration']),
                'swing_duration': float(cycle['swing_duration']),
                'cycle_duration': float(cycle['cycle_duration'])
            }
            for cycle in phase_results.get('gait_cycles', [])
        ],
    }
    
    return results


def generate_gait_report(metrics: Dict[str, Any]) -> str:
    """
    Generate a human-readable gait analysis report.
    """
    report = []
    report.append("=" * 60)
    report.append("GAIT ANALYSIS REPORT")
    report.append("=" * 60)
    
    # Temporal Parameters
    report.append("\n--- TEMPORAL PARAMETERS ---")
    if metrics.get('detected_steps'):
        report.append(f"Total Steps Detected: {metrics['detected_steps']}")
    if metrics.get('cadence_spm'):
        report.append(f"Cadence: {metrics['cadence_spm']:.1f} steps/min")
        normal = " (Normal: 100-120 spm)" if 100 <= metrics['cadence_spm'] <= 120 else " (Outside normal range)"
        report.append(normal)
    if metrics.get('mean_step_time_s'):
        report.append(f"Mean Step Time: {metrics['mean_step_time_s']:.2f} s")
    if metrics.get('step_asymmetry_cv'):
        report.append(f"Step Time Variability (CV): {metrics['step_asymmetry_cv']:.1f}%")
        if metrics['step_asymmetry_cv'] < 3:
            report.append("  → Very consistent stepping")
        elif metrics['step_asymmetry_cv'] < 10:
            report.append("  → Normal variability")
        else:
            report.append("  → High variability (may indicate asymmetry)")
    
    # Gait Phases
    report.append("\n--- GAIT PHASE PARAMETERS ---")
    if metrics.get('mean_stance_time'):
        report.append(f"Mean Stance Time: {metrics['mean_stance_time']:.2f} s")
    if metrics.get('mean_swing_time'):
        report.append(f"Mean Swing Time: {metrics['mean_swing_time']:.2f} s")
    if metrics.get('swing_stance_ratio'):
        report.append(f"Swing/Stance Ratio: {metrics['swing_stance_ratio']:.2f}")
        report.append("  (Normal: ~0.67, i.e., 40% swing, 60% stance)")
    if metrics.get('stance_percentage'):
        report.append(f"Stance Phase: {metrics['stance_percentage']:.1f}%")
    if metrics.get('swing_percentage'):
        report.append(f"Swing Phase: {metrics['swing_percentage']:.1f}%")
    
    # Kinematic Parameters
    report.append("\n--- KINEMATIC PARAMETERS ---")
    if metrics.get('mean_knee_angle_deg'):
        report.append(f"Mean Knee Angle: {metrics['mean_knee_angle_deg']:.1f}°")
    if metrics.get('knee_rom_deg'):
        report.append(f"Knee Range of Motion: {metrics['knee_rom_deg']:.1f}°")
        report.append("  (Normal walking: 60-70°)")
    if metrics.get('peak_knee_angle_deg'):
        report.append(f"Peak Knee Flexion: {metrics['peak_knee_angle_deg']:.1f}°")
    if metrics.get('min_knee_angle_deg'):
        report.append(f"Minimum Knee Angle: {metrics['min_knee_angle_deg']:.1f}°")

    report.append("\n" + "=" * 60)
    
    return "\n".join(report)

