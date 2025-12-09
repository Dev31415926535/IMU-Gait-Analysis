"""
bilateral_processors.py

Bilateral gait analysis for two-leg IMU setup (thigh + shank per leg).
Processes each leg independently and computes inter-limb symmetry metrics.
"""

from typing import Dict, Any, Tuple, List, Optional
import numpy as np
from scipy.signal import find_peaks, medfilt, butter, filtfilt
from scipy.interpolate import interp1d
import warnings
warnings.filterwarnings('ignore')

# Import single-leg processing functions
from processors import (
    process_packet_accel_angle, 
    compute_stream_metrics, 
    GaitPhaseDetector,
    calculate_joint_kinematics,
    estimate_step_asymmetry
)

__all__ = [
    "process_bilateral_packet", 
    "compute_bilateral_metrics",
    "calculate_gait_symmetry"
]

def safe_round(value, ndigits=1, default=0.0):
    if value is None:
        return default
    try:
        return round(value, ndigits)
    except:
        return default

def process_bilateral_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a bilateral packet containing data from both legs.
    
    Expected packet structure:
    {
        "timestamp": int,
        "left_leg": {
            "thigh": {...IMU data...},
            "shank": {...IMU data...}
        },
        "right_leg": {
            "thigh": {...IMU data...},
            "shank": {...IMU data...}
        }
    }
    
    Returns dict with angles and kinematics for both legs.
    """
    results = {
        "timestamp": packet.get("timestamp"),
        "left": {},
        "right": {}
    }
    
    # Process left leg
    left_packet = {
        "IMU1": packet["left_leg"]["thigh"],
        "IMU2": packet["left_leg"]["shank"]
    }
    left_angle, left_valid = process_packet_accel_angle(left_packet)
    results["left"]["knee_angle"] = left_angle
    results["left"]["valid"] = left_valid
    results["left"]["kinematics"] = calculate_joint_kinematics(left_packet)
    
    # Process right leg
    right_packet = {
        "IMU1": packet["right_leg"]["thigh"],
        "IMU2": packet["right_leg"]["shank"]
    }
    right_angle, right_valid = process_packet_accel_angle(right_packet)
    results["right"]["knee_angle"] = right_angle
    results["right"]["valid"] = right_valid
    results["right"]["kinematics"] = calculate_joint_kinematics(right_packet)
    
    # Calculate instantaneous symmetry
    if left_valid and right_valid and left_angle is not None and right_angle is not None:
        results["angle_difference"] = abs(left_angle - right_angle)
        results["angle_symmetry_index"] = 100 * (1 - abs(left_angle - right_angle) / max(abs(left_angle), abs(right_angle), 1))
    else:
        results["angle_difference"] = None
        results["angle_symmetry_index"] = None
    
    return results


def calculate_gait_symmetry(
    left_metrics: Dict[str, Any],
    right_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate gait symmetry indices between left and right legs.
    
    Uses various symmetry indices from literature:
    - Symmetry Index (SI) = 2 * |left - right| / (left + right) * 100
    - Symmetry Ratio (SR) = min(left, right) / max(left, right)
    - Asymmetry Index (AI) = (left - right) / 0.5*(left + right) * 100
    """
    symmetry = {}
    
    def calc_si(left_val, right_val):
        """Symmetry Index"""
        if left_val is None or right_val is None:
            return None
        sum_val = left_val + right_val
        if abs(sum_val) < 0.001:
            return 0.0
        return 200 * abs(left_val - right_val) / sum_val
    
    def calc_sr(left_val, right_val):
        """Symmetry Ratio"""
        if left_val is None or right_val is None:
            return None
        max_val = max(abs(left_val), abs(right_val))
        if max_val < 0.001:
            return 1.0
        return min(abs(left_val), abs(right_val)) / max_val
    
    def calc_ai(left_val, right_val):
        """Asymmetry Index (directional)"""
        if left_val is None or right_val is None:
            return None
        mean_val = 0.5 * (left_val + right_val)
        if abs(mean_val) < 0.001:
            return 0.0
        return 100 * (left_val - right_val) / mean_val
    
    # Temporal symmetry
    if left_metrics.get("cadence_spm") and right_metrics.get("cadence_spm"):
        symmetry["cadence_si"] = calc_si(left_metrics["cadence_spm"], right_metrics["cadence_spm"])
        symmetry["cadence_sr"] = calc_sr(left_metrics["cadence_spm"], right_metrics["cadence_spm"])
    
    if left_metrics.get("mean_step_time_s") and right_metrics.get("mean_step_time_s"):
        symmetry["step_time_si"] = calc_si(left_metrics["mean_step_time_s"], right_metrics["mean_step_time_s"])
        symmetry["step_time_sr"] = calc_sr(left_metrics["mean_step_time_s"], right_metrics["mean_step_time_s"])
    
    # Stance/Swing symmetry
    # if left_metrics.get("stance_percentage") and right_metrics.get("stance_percentage"):
    #     symmetry["stance_si"] = calc_si(left_metrics["stance_percentage"], right_metrics["stance_percentage"])
    #     symmetry["stance_ai"] = calc_ai(left_metrics["stance_percentage"], right_metrics["stance_percentage"])
    
    # if left_metrics.get("swing_percentage") and right_metrics.get("swing_percentage"):
    #     symmetry["swing_si"] = calc_si(left_metrics["swing_percentage"], right_metrics["swing_percentage"])
    #     symmetry["swing_ai"] = calc_ai(left_metrics["swing_percentage"], right_metrics["swing_percentage"])
    
    # if left_metrics.get("swing_stance_ratio") and right_metrics.get("swing_stance_ratio"):
    #     symmetry["swing_stance_ratio_si"] = calc_si(left_metrics["swing_stance_ratio"], right_metrics["swing_stance_ratio"])
    
    # # Kinematic symmetry
    # if left_metrics.get("knee_rom_deg") and right_metrics.get("knee_rom_deg"):
    #     symmetry["rom_si"] = calc_si(left_metrics["knee_rom_deg"], right_metrics["knee_rom_deg"])
    #     symmetry["rom_sr"] = calc_sr(left_metrics["knee_rom_deg"], right_metrics["knee_rom_deg"])
    #     symmetry["rom_ai"] = calc_ai(left_metrics["knee_rom_deg"], right_metrics["knee_rom_deg"])
    
    # if left_metrics.get("peak_knee_angle_deg") and right_metrics.get("peak_knee_angle_deg"):
    #     symmetry["peak_angle_si"] = calc_si(left_metrics["peak_knee_angle_deg"], right_metrics["peak_knee_angle_deg"])
    #     symmetry["peak_angle_diff"] = abs(left_metrics["peak_knee_angle_deg"] - right_metrics["peak_knee_angle_deg"])
    
    # Overall gait symmetry score (0-100, 100 = perfect symmetry)
    si_values = [v for k, v in symmetry.items() if k.endswith("_si") and v is not None]
    if si_values:
        # Convert SI to symmetry score (SI of 0 = 100% symmetry)
        symmetry["overall_symmetry_score"] = max(0, 100 - np.mean(si_values))
    else:
        symmetry["overall_symmetry_score"] = None
    
    # Classify asymmetry level
    if symmetry.get("overall_symmetry_score") is not None:
        score = symmetry["overall_symmetry_score"]
        if score >= 90:
            symmetry["symmetry_classification"] = "Excellent symmetry"
        elif score >= 85:
            symmetry["symmetry_classification"] = "Good symmetry"
        # elif score >= 70:
        #     symmetry["symmetry_classification"] = "Mild asymmetry"
        # elif score >= 60:
        #     symmetry["symmetry_classification"] = "Moderate asymmetry"
        else:
            symmetry["symmetry_classification"] = " Asymmetry: needs improvement"
    
    return symmetry


def compute_bilateral_metrics(
    packets: List[Dict[str, Any]], 
    sampling_rate: float = 10.0
) -> Dict[str, Any]:
    """
    Compute gait metrics for bilateral IMU data.
    
    Returns dict with:
    - left_metrics: Complete metrics for left leg
    - right_metrics: Complete metrics for right leg  
    - symmetry: Inter-limb symmetry indices
    - cross_correlation: Temporal coupling between legs
    """
    if not packets:
        return {}
    
    # Separate packets into left and right leg data
    left_packets = []
    right_packets = []
    timestamps = []
    
    for p in packets:
        if "left_leg" in p and "right_leg" in p:
            # Convert to single-leg packet format for existing processors
            left_packets.append({
                "IMU1": p["left_leg"]["thigh"],
                "IMU2": p["left_leg"]["shank"]
            })
            right_packets.append({
                "IMU1": p["right_leg"]["thigh"],
                "IMU2": p["right_leg"]["shank"]
            })
            timestamps.append(p.get("timestamp", 0))
    
    # Compute metrics for each leg using existing single-leg processor
    left_metrics = compute_stream_metrics(left_packets, sampling_rate=sampling_rate)
    right_metrics = compute_stream_metrics(right_packets, sampling_rate=sampling_rate)
    
    # Calculate inter-limb symmetry
    symmetry_metrics = calculate_gait_symmetry(left_metrics, right_metrics)
    
    # Calculate cross-correlation between knee angles
    cross_corr_metrics = {}
    if left_metrics.get("angles") and right_metrics.get("angles"):
        left_angles = np.array([a if a is not None else np.nan for a in left_metrics["angles"]])
        right_angles = np.array([a if a is not None else np.nan for a in right_metrics["angles"]])
        
        # Remove NaN values for correlation
        valid_idx = ~(np.isnan(left_angles) | np.isnan(right_angles))
        if np.sum(valid_idx) > 10:
            left_valid = left_angles[valid_idx]
            right_valid = right_angles[valid_idx]
            
            # Normalize signals
            left_norm = (left_valid - np.mean(left_valid)) / (np.std(left_valid) + 1e-9)
            right_norm = (right_valid - np.mean(right_valid)) / (np.std(right_valid) + 1e-9)
            
            # Cross-correlation
            correlation = np.correlate(left_norm, right_norm, mode='same')
            max_corr_idx = np.argmax(np.abs(correlation))
            lag_samples = max_corr_idx - len(correlation) // 2
            lag_time = lag_samples / sampling_rate
            
            cross_corr_metrics = {
                "max_correlation": float(np.max(np.abs(correlation)) / len(left_norm)),
                "phase_lag_samples": int(lag_samples),
                "phase_lag_seconds": float(lag_time),
                "correlation_coefficient": float(np.corrcoef(left_valid, right_valid)[0, 1])
            }
    
    # Detect coordinated steps (when both legs show peaks close in time)
    coordinated_steps = detect_coordinated_steps(
        left_metrics.get("step_times", []),
        right_metrics.get("step_times", []),
        max_time_diff=0.5  # 500ms window for coordination
    )
    
    # Compile results
    results = {
        # Individual leg metrics
        "left_leg": left_metrics,
        "right_leg": right_metrics,
        
        # Symmetry metrics
        "symmetry": symmetry_metrics,
        
        # Cross-correlation metrics
        "cross_correlation": cross_corr_metrics,
        
        # Step coordination
        "coordinated_steps": coordinated_steps,
        
        # Global metrics (averaged across legs)
        "global_metrics": calculate_global_metrics(left_metrics, right_metrics),
        
        # Timestamps
        "timestamps": timestamps[:len(left_packets)]
    }
    
    return results


def detect_coordinated_steps(
    left_step_times: List[float],
    right_step_times: List[float],
    max_time_diff: float = 0.5
) -> Dict[str, Any]:
    """
    Detect coordinated stepping patterns between legs.
    """
    if not left_step_times or not right_step_times:
        return {}
    
    coordinated = []
    left_only = []
    right_only = []
    
    left_used = set()
    right_used = set()
    
    # Find coordinated steps
    for i, left_t in enumerate(left_step_times):
        matched = False
        for j, right_t in enumerate(right_step_times):
            if j not in right_used and abs(left_t - right_t) < max_time_diff:
                coordinated.append({
                    "left_time": left_t,
                    "right_time": right_t,
                    "time_diff": right_t - left_t,
                    "leading_leg": "left" if left_t < right_t else "right"
                })
                left_used.add(i)
                right_used.add(j)
                matched = True
                break
        if not matched:
            left_only.append(left_t)
    
    # Find unmatched right steps
    for j, right_t in enumerate(right_step_times):
        if j not in right_used:
            right_only.append(right_t)
    
    # Calculate coordination index
    total_steps = len(left_step_times) + len(right_step_times)
    coord_steps = 2 * len(coordinated)  # Each coordinated pair counts as 2 steps
    coordination_index = 100 * coord_steps / total_steps if total_steps > 0 else 0
    
    return {
        "coordinated_pairs": coordinated,
        "left_only_steps": left_only,
        "right_only_steps": right_only,
        "num_coordinated": len(coordinated),
        "num_left_only": len(left_only),
        "num_right_only": len(right_only),
        "coordination_index": coordination_index,
        "mean_time_diff": np.mean([abs(c["time_diff"]) for c in coordinated]) if coordinated else None
    }


def calculate_global_metrics(
    left_metrics: Dict[str, Any],
    right_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate global metrics averaged across both legs.
    """
    global_metrics = {}
    
    # Average temporal metrics
    if left_metrics.get("cadence_spm") and right_metrics.get("cadence_spm"):
        global_metrics["mean_cadence_spm"] = (left_metrics["cadence_spm"] + right_metrics["cadence_spm"]) / 2
    
    if left_metrics.get("detected_steps") and right_metrics.get("detected_steps"):
        global_metrics["total_steps"] = left_metrics["detected_steps"] + right_metrics["detected_steps"]
    
    # Average kinematic metrics
    if left_metrics.get("knee_rom_deg") and right_metrics.get("knee_rom_deg"):
        global_metrics["mean_rom_deg"] = (left_metrics["knee_rom_deg"] + right_metrics["knee_rom_deg"]) / 2
    
    if left_metrics.get("peak_knee_angle_deg") and right_metrics.get("peak_knee_angle_deg"):
        global_metrics["mean_peak_angle_deg"] = (left_metrics["peak_knee_angle_deg"] + right_metrics["peak_knee_angle_deg"]) / 2
    
    # Average phase metrics
    if left_metrics.get("stance_percentage") and right_metrics.get("stance_percentage"):
        global_metrics["mean_stance_percentage"] = (left_metrics["stance_percentage"] + right_metrics["stance_percentage"]) / 2
    
    if left_metrics.get("swing_percentage") and right_metrics.get("swing_percentage"):
        global_metrics["mean_swing_percentage"] = (left_metrics["swing_percentage"] + right_metrics["swing_percentage"]) / 2
    
    return global_metrics


import json

def generate_bilateral_gait_report(metrics: dict) -> dict:
    """
    Generate a comprehensive bilateral gait analysis report in JSON format.
    Includes mean knee angles for both legs.
    """
    report = {
        "report_type": "bilateral_gait_analysis",
        "global_metrics": {},
        "left_leg": {},
        "right_leg": {},
        "symmetry": {},
        "step_coordination": {},
        "inter_limb_correlation": {},
        "clinical_interpretation": {}
    }
    
    # Global metrics
    if metrics.get("global_metrics"):
        gm = metrics["global_metrics"]
        report["global_metrics"] = {
            "total_steps": gm.get("total_steps"),
            "mean_cadence_spm": safe_round(gm.get("mean_cadence_spm")),
            "mean_rom_deg": safe_round(gm.get("mean_rom_deg")),
            "mean_peak_angle_deg": safe_round(gm.get("mean_peak_angle_deg")),
            "mean_stance_percentage": safe_round(gm.get("mean_stance_percentage")),
            "mean_swing_percentage": safe_round(gm.get("mean_swing_percentage"))

        }
    
    # Left leg metrics with mean knee angle
    if metrics.get("left_leg"):
        lm = metrics["left_leg"]
        
        # Calculate mean knee angle from angles array
        mean_knee_angle_left = None
        if lm.get("angles"):
            valid_angles = [a for a in lm["angles"] if a is not None]
            if valid_angles:
                mean_knee_angle_left = round(sum(valid_angles) / len(valid_angles), 2)
        
        report["left_leg"] = {
            "detected_steps": lm.get("detected_steps", 0) ,
            "cadence_spm": safe_round(lm.get("cadence_spm")),
            "knee_rom_deg": safe_round(lm.get("knee_rom_deg")),
            "peak_knee_angle_deg": safe_round(lm.get("peak_knee_angle_deg")),
            "stance_percentage": safe_round(lm.get("stance_percentage")),
            "swing_percentage": safe_round(lm.get("swing_percentage")),
            "mean_step_time_s": safe_round(lm.get("mean_step_time_s"), 3),
            "swing_stance_ratio": safe_round(lm.get("swing_stance_ratio"), 2)
        }
    
    # Right leg metrics with mean knee angle
    if metrics.get("right_leg"):
        rm = metrics["right_leg"]
        
        # Calculate mean knee angle from angles array
        mean_knee_angle_right = None
        if rm.get("angles"):
            valid_angles = [a for a in rm["angles"] if a is not None]
            if valid_angles:
                mean_knee_angle_right = round(sum(valid_angles) / len(valid_angles), 2)
        
        report["right_leg"] = {
            "detected_steps": rm.get("detected_steps", 0) ,
            "cadence_spm": safe_round(rm.get("cadence_spm")),
            "knee_rom_deg": safe_round(rm.get("knee_rom_deg")),
            "peak_knee_angle_deg": safe_round(rm.get("peak_knee_angle_deg")),
            "stance_percentage": safe_round(rm.get("stance_percentage")),
            "swing_percentage": safe_round(rm.get("swing_percentage")),
            "mean_step_time_s": safe_round(rm.get("mean_step_time_s"), 3),
            "swing_stance_ratio": safe_round(rm.get("swing_stance_ratio"), 2)
        }
    
    # Mean knee angle difference
    if report["left_leg"].get("mean_knee_angle_deg") is not None and \
       report["right_leg"].get("mean_knee_angle_deg") is not None:
        report["global_metrics"]["mean_knee_angle_difference_deg"] = safe_round(
            abs(report["left_leg"]["mean_knee_angle_deg"] - 
                report["right_leg"]["mean_knee_angle_deg"]), 2
        )
    
    # Symmetry analysis
    if metrics.get("symmetry"):
        sym = metrics["symmetry"]
        report["symmetry"] = {
            "overall_symmetry_score": round(sym.get("overall_symmetry_score", 0), 1),
            "symmetry_classification": sym.get("symmetry_classification"),
        }
    
    # Step coordination
    if metrics.get("coordinated_steps"):
        cs = metrics["coordinated_steps"]
        report["step_coordination"] = {
            "coordination_index": round(cs.get("coordination_index", 0), 1),
            "num_coordinated_pairs": cs.get("num_coordinated", 0),
            "num_left_only_steps": cs.get("num_left_only", 0),
            "num_right_only_steps": cs.get("num_right_only", 0),
            "mean_time_diff_ms": round(cs.get("mean_time_diff", 0) * 1000, 0) if cs.get("mean_time_diff") is not None else None
        }
    
    # Cross-correlation
    if metrics.get("cross_correlation"):
        cc = metrics["cross_correlation"]
        report["inter_limb_correlation"] = {
            "correlation_coefficient": round(cc.get("correlation_coefficient", 0), 3),
            "phase_lag_ms": round(cc.get("phase_lag_seconds", 0) * 1000, 0) if cc.get("phase_lag_seconds") is not None else None,
            "phase_lag_samples": cc.get("phase_lag_samples"),
            "max_correlation": round(cc.get("max_correlation", 0), 3) if cc.get("max_correlation") is not None else None
        }
    
    # Clinical interpretation
    if metrics.get("symmetry", {}).get("overall_symmetry_score"):
        score = metrics["symmetry"]["overall_symmetry_score"]
        if score >= 85:
            interpretation = "Excellent bilateral symmetry - Normal gait pattern"
            severity = "normal"
        # elif score >= 80:
        #     interpretation = "Good symmetry with minor variations - Within normal limits"
        #     severity = "minor"
        # elif score >= 70:
        #     interpretation = "Mild asymmetry detected - May indicate compensatory patterns"
        #     severity = "mild"
        else:
            interpretation = "Asymmetry - Consider further evaluation"
            severity = "not good"
        
        report["clinical_interpretation"] = {
            "interpretation": interpretation,
            "severity": severity,
            "symmetry_score": round(score, 1)
        }
    
    return report