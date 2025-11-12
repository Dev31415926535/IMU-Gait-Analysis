# src/main.py
import time
import os
import json
import glob
import numpy as np
from ws_reader import IMUWebSocketReader
from imu_joint_angle import IMUJointAngle
from processors import process_packet_accel_angle, compute_stream_metrics
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'recordings')
os.makedirs(DATA_DIR, exist_ok=True)
CALIB_PATH = os.path.join(DATA_DIR, "calibration.npz")


# ---------- Calibration ----------
def calibration_phase(ws, joint_system, num_samples=100, timeout_s=40):
    print("=== Calibration Phase ===")
    imu1 = []
    imu2 = []
    start = time.time()
    while len(imu1) < num_samples and (time.time() - start) < timeout_s:
        pkt = ws.read_packet()
        if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
            imu1.append(pkt['IMU1'])
            imu2.append(pkt['IMU2'])
            if len(imu1) % 10 == 0:
                print(f"Collected {len(imu1)}/{num_samples}")
        else:
            time.sleep(0.01)

    if len(imu1) < 10:
        print("Calibration failed: not enough packets")
        return False, imu1, imu2

    if joint_system.debug:
        joint_system.debug_print_calib_samples(imu1, imu2, max_items=6)

    calib_data = joint_system.collect_calibration_data(imu1, imu2)
    try:
        print("Running axis & offset calibration...")
        joint_system.calibrate(calib_data, n_restarts=6)
        print("Calibration finished (axes+offsets).")
        joint_system.detect_and_set_gyro_scale_from_calib(imu1, imu2, threshold_deg_per_s=20.0)

        try:
            joint_system.persist_path = CALIB_PATH
            joint_system.save_calibration(CALIB_PATH)
        except Exception as e:
            print(f"Warning: failed to save calibration: {e}")

        return True, imu1, imu2
    except Exception as e:
        print(f"Calibration error: {e}")
        return False, imu1, imu2


# ---------- Zeroing ----------
def zeroing_phase(ws, joint_system, window_s=3.5, timeout_s=20.0,
                  sampling_rate_est=10.0, gyro_thresh=0.6):
    print("\n=== Zeroing Phase ===")
    print(f"Please hold the limb still for ~{window_s:.1f}s (timeout {timeout_s}s).")
    window_n = max(5, int(window_s * sampling_rate_est))
    imu1_window, imu2_window = [], []
    start = time.time()
    last_print = start

    while time.time() - start < timeout_s:
        pkt = ws.read_packet()
        if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
            imu1_window.append(pkt['IMU1'])
            imu2_window.append(pkt['IMU2'])
            if len(imu1_window) > window_n:
                imu1_window.pop(0)
                imu2_window.pop(0)

            if len(imu1_window) >= window_n:
                mags = []
                for r1, r2 in zip(imu1_window, imu2_window):
                    g1 = np.array([r1['Gx'], r1['Gy'], r1['Gz']], float) - joint_system.g1_bias
                    g2 = np.array([r2['Gx'], r2['Gy'], r2['Gz']], float) - joint_system.g2_bias
                    mags.append(np.linalg.norm(g1) + np.linalg.norm(g2))
                g_mean = float(np.mean(mags))
                now = time.time()
                if now - last_print > 1.0:
                    print(f"[zeroing] window samples={len(imu1_window)}, mean combined gyro mag={g_mean:.3f}")
                    last_print = now
                if g_mean < gyro_thresh:
                    try:
                        joint_system.set_zero_reference_from_window(imu1_window, imu2_window, gyro_thresh=gyro_thresh)
                        joint_system.reestimate_gyro_bias_from_window(imu1_window, imu2_window)
                        if joint_system.persist_path:
                            joint_system.save_calibration(joint_system.persist_path)
                        print("[zeroing] Zero set and gyro bias re-estimated.")
                        return True
                    except Exception as e:
                        print(f"[zeroing] attempt failed: {e}")
        else:
            time.sleep(0.005)
    print("[zeroing] timed out (stillness not captured).")
    return False

def measurement_phase(
    ws,
    joint_system=None,
    duration_s=30,
    sampling_rate_est=50.0,
    out_filename="joint_angles.csv",
    rezero_on_stillness=True,
    rezero_window_s=1.5,
    rezero_gyro_thresh=0.5,
    rezero_cooldown_s=5.0
):
    """
    Collect measurement packets and save raw + computed angles.

    Behavior:
    - Collects packets from ws for duration_s
    - Performs optional mid-run re-zero (unchanged)
    - Computes metrics via compute_stream_metrics(packets, sampling_rate=sampling_rate_est)
    - Saves raw JSONL of packets
    - Saves CSV where the primary angle column is the fused/printed angle
      (joint_system.calculate_angle) — this guarantees CSV matches terminal output.
    - Also writes accel-only / metrics angles as a comparison column.
    """

    import time, os, json
    import numpy as np

    print("\n=== Measurement Phase ===")
    packets = []
    start_time = time.time()
    end_time = start_time + duration_s
    last_print = start_time

    window_n = max(3, int(rezero_window_s * sampling_rate_est))
    imu1_window, imu2_window = [], []
    last_rezero = -9999.0

    # Collect packets
    while time.time() < end_time:
        pkt = None
        try:
            pkt = ws.read_packet()
        except Exception:
            pkt = None

        if pkt is None:
            now = time.time()
            if now - last_print >= 1.0:
                elapsed = now - start_time
                print(f"[measurement] elapsed {elapsed:.1f}s / {duration_s}s, packets={len(packets)}")
                last_print = now
            time.sleep(0.005)
            continue

        # Append if contains IMU data
        if 'IMU1' in pkt and 'IMU2' in pkt:
            packets.append(pkt)
            imu1_window.append(pkt['IMU1'])
            imu2_window.append(pkt['IMU2'])
            if len(imu1_window) > window_n:
                imu1_window.pop(0)
                imu2_window.pop(0)

        # ---- NEW: live angle print for frontend ----
        try:
            fused = None
            if joint_system is not None:
                fused = joint_system.calculate_angle(pkt['IMU1'], pkt['IMU2'])
            if fused is not None:
                print(f"STREAM_DATA {time.time() - start_time:.3f},{fused:.3f}", flush=True)
        except Exception:
            pass

            # mid-run re-zero (same logic you had previously)
            if rezero_on_stillness and len(imu1_window) >= window_n and (time.time() - last_rezero) > rezero_cooldown_s:
                try:
                    # compute gyro magnitude across window (subtract bias if joint_system provides bias)
                    mags = []
                    for r1, r2 in zip(imu1_window, imu2_window):
                        # attempt to apply biases if joint_system has them, otherwise use raw
                        try:
                            g1 = np.array([r1['Gx'], r1['Gy'], r1['Gz']], dtype=float)
                            g2 = np.array([r2['Gx'], r2['Gy'], r2['Gz']], dtype=float)
                            if getattr(joint_system, 'g1_bias', None) is not None:
                                g1 = g1 - joint_system.g1_bias
                            if getattr(joint_system, 'g2_bias', None) is not None:
                                g2 = g2 - joint_system.g2_bias
                            mags.append(np.linalg.norm(g1) + np.linalg.norm(g2))
                        except Exception:
                            pass
                    g_mean = float(np.mean(mags)) if len(mags) > 0 else 1e9
                    if g_mean < rezero_gyro_thresh:
                        try:
                            # call your existing rezero helpers on joint_system (if they exist)
                            if joint_system is not None and hasattr(joint_system, "reestimate_gyro_bias_from_window"):
                                joint_system.reestimate_gyro_bias_from_window(imu1_window, imu2_window)
                            if joint_system is not None and hasattr(joint_system, "set_zero_reference_from_window"):
                                joint_system.set_zero_reference_from_window(imu1_window, imu2_window, gyro_thresh=rezero_gyro_thresh)
                            last_rezero = time.time()
                            # try persist if supported
                            try:
                                if getattr(joint_system, "persist_path", None):
                                    joint_system.save_calibration(joint_system.persist_path)
                            except Exception:
                                pass
                            print(f"[measurement] mid-run re-zero at t={time.time()-start_time:.1f}s")
                        except Exception as e:
                            print(f"[measurement] mid-run re-zero failed: {e}")
                except Exception:
                    pass

        # small sleep to avoid busy loop (tweak as your ws.read_packet rate)
        time.sleep(0.001)

    # Save raw jsonl (unchanged)
    ts = int(time.time())
    try:
        raw_path = os.path.join(DATA_DIR, f"raw_{ts}.jsonl")
        with open(raw_path, 'w') as f:
            for p in packets:
                f.write(json.dumps(p) + "\n")
        print(f"Saved raw packets to {raw_path} (N={len(packets)})")
    except Exception as e:
        print(f"Warning: failed to save raw jsonl: {e}")

    # --- Compute metrics first (this is what will be printed) ---
    try:
        # If your compute_stream_metrics supports joint_system param, pass it; if not, still works.
        try:
            metrics = compute_stream_metrics(packets, sampling_rate=sampling_rate_est, joint_system=joint_system)
        except TypeError:
            # fallback if compute_stream_metrics doesn't accept joint_system param
            metrics = compute_stream_metrics(packets, sampling_rate=sampling_rate_est)
    except Exception as e:
        print(f"Error computing metrics: {e}")
        metrics = {}

    # Print the summary exactly as before
    print("Summary metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    # --- Build fused_angles exactly like terminal printing (so CSV matches terminal) ---
    fused_angles = []
    for p in packets:
        fused = None
        if joint_system is not None:
            try:
                # Use the exact call your terminal uses to print the live angle
                # Some joint_system implementations use calculate_angle(IMU1, IMU2)
                fused = joint_system.calculate_angle(p['IMU1'], p['IMU2'])
            except Exception:
                fused = None
        fused_angles.append(fused)

    # metric angles (accel-only or whatever compute_stream_metrics returned)
    metric_angles = metrics.get("angles", None)
    times = metrics.get("times", None)
    if times is None:
        times = [i / sampling_rate_est for i in range(len(fused_angles))]

    # Write CSV so first numeric angle column is the fused (printed) angle.
    try:
        out_path = os.path.join(DATA_DIR, out_filename)
        with open(out_path, 'w') as f:
            f.write("time_s,angle_printed_fused_deg,angle_metrics_deg\n")
            for i in range(len(fused_angles)):
                t = times[i] if i < len(times) else (i / sampling_rate_est)
                a_fused = fused_angles[i]
                a_metrics = metric_angles[i] if (metric_angles is not None and i < len(metric_angles)) else None
                a_fused_s = "" if a_fused is None else f"{float(a_fused):.6f}"
                a_metrics_s = "" if a_metrics is None else f"{float(a_metrics):.6f}"
                f.write(f"{t:.3f},{a_fused_s},{a_metrics_s}\n")
        print(f"Saved CSV with printed (fused) angles to {out_path} (N={len(fused_angles)})")
    except Exception as e:
        print(f"Failed to save CSV: {e}")

    return metrics


def offline_test_on_jsonl(path, force_recalib=False, sampling_rate_est=10.0):
    files = glob.glob(path)
    if len(files) == 0:
        print("No files found for pattern:", path)
        return
    f = files[-1]
    print("Using file:", f)
    packets = []
    with open(f, 'r') as fh:
        for line in fh:
            try:
                packets.append(json.loads(line.strip()))
            except Exception:
                pass
    if len(packets) == 0:
        print("No packets in file.")
        return

    joint_system = IMUJointAngle(delta_t=1.0/sampling_rate_est, alpha=0.92, adaptive_alpha=True,
                                output_smooth_alpha=0.12, persist_path=CALIB_PATH, debug=True)
    loaded = False
    if not force_recalib:
        loaded = joint_system.load_calibration(CALIB_PATH, load_zero=False)

    imu1 = [p['IMU1'] for p in packets[:160] if 'IMU1' in p]
    imu2 = [p['IMU2'] for p in packets[:160] if 'IMU2' in p]
    if not loaded and len(imu1) >= 10:
        try:
            calib_arr = joint_system.collect_calibration_data(imu1, imu2)
            joint_system.calibrate(calib_arr, n_restarts=6)
            joint_system.detect_and_set_gyro_scale_from_calib(imu1, imu2, threshold_deg_per_s=20.0)
            joint_system.persist_path = CALIB_PATH
            joint_system.save_calibration(CALIB_PATH)
        except Exception as e:
            print("Offline calibration failed:", e)

    # deterministic zero: use first ~3s window
    window_n = max(5, int(3.0 * sampling_rate_est))
    imu1_window = [p['IMU1'] for p in packets[:window_n] if 'IMU1' in p]
    imu2_window = [p['IMU2'] for p in packets[:window_n] if 'IMU2' in p]
    try:
        joint_system.set_zero_reference_from_window(imu1_window, imu2_window, gyro_thresh=0.8)
        print("[offline] zero set from first 3s window.")
    except Exception as e:
        print("[offline] zeroing failed:", e)

    angles = []
    for p in packets:
        try:
            a = joint_system.calculate_angle(p['IMU1'], p['IMU2'])
        except Exception:
            a = None
        angles.append(a)

    valid = [a for a in angles if a is not None]
    if not valid:
        print("No valid angles.")
        return
    print(f"[offline] mean={np.mean(valid):.3f} deg, std={np.std(valid):.3f} deg, peak={np.max(valid):.3f} deg (N={len(valid)})")

# ---------- Run ----------
def run(esp_ip):
    if os.path.exists(CALIB_PATH):
        try:
            os.remove(CALIB_PATH)
            print("[info] Removed old calibration file; forcing recalibration for this trial.")
        except Exception as e:
            print(f"[info] could not remove calibration file: {e}")

    ws = IMUWebSocketReader(esp_ip)
    if not ws.connect():
        print("Cannot connect to ESP32. Exiting.")
        return

    joint_system = IMUJointAngle(delta_t=0.1, alpha=0.92, adaptive_alpha=True,
                                 output_smooth_alpha=0.12, persist_path=CALIB_PATH, debug=True)

    try:
        ok, imu1_cal, imu2_cal = calibration_phase(ws, joint_system, num_samples=100, timeout_s=40)
        if not ok:
            print("Calibration incomplete; continuing with best-effort.")

        zero_ok = zeroing_phase(ws, joint_system, window_s=3.5, timeout_s=20.0,
                                sampling_rate_est=10.0, gyro_thresh=0.6)
        if not zero_ok:
            try:
                if imu1_cal and imu2_cal and len(imu1_cal) >= 20:
                    joint_system.force_zero_from_accel_window(imu1_cal[:60], imu2_cal[:60], use_median=True)
                    joint_system.reestimate_gyro_bias_from_window(imu1_cal[:60], imu2_cal[:60])
                    print("[zeroing] fallback: forced accel-median zero from calibration frames.")
            except Exception as e:
                print(f"[zeroing] fallback failed: {e}")

        print("[preview] sampling a short preview (hold still)...")
        preview_angles = []
        for _ in range(20):
            pkt = ws.read_packet()
            if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
                try:
                    preview_angles.append(joint_system.calculate_angle(pkt['IMU1'], pkt['IMU2']))
                except Exception:
                    pass
            else:
                time.sleep(0.02)
        valid = [a for a in preview_angles if a is not None]
        if valid:
            print(f"[post-zero preview] mean={np.mean(valid):.3f} deg, std={np.std(valid):.3f} deg, n={len(valid)}")
        else:
            print("[post-zero preview] no valid preview angles")

        if os.getenv("AUTO_START", "0") != "1":
            input("Press Enter to start measurement (will run 30s)...")
        else:
            print("AUTO_START=1 — starting measurement.")

        measurement_phase(ws, joint_system=joint_system, duration_s=30, sampling_rate_est=10.0)
    finally:
        ws.close()


if __name__ == "__main__":
    ESP_IP = os.getenv("ESP_IP")
    if not ESP_IP:
        print("Warning: ESP_IP not set in environment.")
    print(f"Using ESP_IP = {ESP_IP}")
    run(ESP_IP)
