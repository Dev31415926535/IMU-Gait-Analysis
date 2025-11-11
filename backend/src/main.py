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

def calibration_phase(ws, joint_system, num_samples=100, timeout_s=40):
    """
    Collect calibration samples and run calibration.
    """
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

        # persist calibration
        try:
            joint_system.persist_path = CALIB_PATH
            joint_system.save_calibration(CALIB_PATH)
        except Exception as e:
            print(f"Warning: failed to save calibration: {e}")

        return True, imu1, imu2
    except Exception as e:
        print(f"Calibration error: {e}")
        return False, imu1, imu2

def zeroing_phase(ws, joint_system, window_s=3.5, timeout_s=20.0, sampling_rate_est=10.0, gyro_thresh=0.6):
    """
    Capture a still window and set zero reference.
    """
    print("\n=== Zeroing Phase ===")
    print(f"Please hold the limb still for ~{window_s:.1f}s (timeout {timeout_s}s).")
    window_n = max(5, int(window_s * sampling_rate_est))
    imu1_window = []
    imu2_window = []
    start = time.time()
    last_print = start

    while time.time() - start < timeout_s:
        pkt = ws.read_packet()
        if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
            imu1_window.append(pkt['IMU1'])
            imu2_window.append(pkt['IMU2'])
            if len(imu1_window) > window_n:
                imu1_window.pop(0); imu2_window.pop(0)

            if len(imu1_window) >= window_n:
                mags = []
                for r1, r2 in zip(imu1_window, imu2_window):
                    g1 = np.array([r1['Gx'], r1['Gy'], r1['Gz']], dtype=float) - joint_system.g1_bias
                    g2 = np.array([r2['Gx'], r2['Gy'], r2['Gz']], dtype=float) - joint_system.g2_bias
                    mags.append(np.linalg.norm(g1) + np.linalg.norm(g2))
                g_mean = float(np.mean(mags))
                now = time.time()
                if now - last_print > 1.0:
                    print(f"[zeroing] window samples={len(imu1_window)}, mean combined gyro mag={g_mean:.3f}")
                    last_print = now
                if g_mean < gyro_thresh:
                    try:
                        joint_system.set_zero_reference_from_window(imu1_window, imu2_window, gyro_thresh=gyro_thresh)
                        # re-bias from window
                        joint_system.reestimate_gyro_bias_from_window(imu1_window, imu2_window)
                        # persist zero and biases
                        try:
                            if joint_system.persist_path:
                                joint_system.save_calibration(joint_system.persist_path)
                        except Exception:
                            pass
                        print("[zeroing] Zero set and gyro bias re-estimated.")
                        return True
                    except Exception as e:
                        print(f"[zeroing] attempt failed: {e} (continuing to search)")
        else:
            time.sleep(0.005)
    print("[zeroing] timed out (stillness not captured).")
    return False

def measurement_phase(ws, joint_system=None, duration_s=30, sampling_rate_est=10.0, out_filename="joint_angles.csv",
                      rezero_on_stillness=True, rezero_window_s=1.5, rezero_gyro_thresh=0.5, rezero_cooldown_s=5.0):
    """
    Collect measurement packets and save raw + computed angles.
    """
    print("\n=== Measurement Phase ===")
    packets = []
    start_time = time.time()
    end_time = start_time + duration_s
    last_print = start_time

    window_n = max(3, int(rezero_window_s * sampling_rate_est))
    imu1_window = []
    imu2_window = []
    last_rezero = -9999.0

    while time.time() < end_time:
        pkt = ws.read_packet()
        if pkt is None:
            now = time.time()
            if now - last_print >= 1.0:
                elapsed = now - start_time
                print(f"[measurement] elapsed {elapsed:.1f}s / {duration_s}s, packets={len(packets)}")
                last_print = now
            time.sleep(0.005)
            continue

        if 'IMU1' in pkt and 'IMU2' in pkt:
            packets.append(pkt)
            imu1_window.append(pkt['IMU1']); imu2_window.append(pkt['IMU2'])
            if len(imu1_window) > window_n:
                imu1_window.pop(0); imu2_window.pop(0)

            # mid-run re-zero
            if rezero_on_stillness and len(imu1_window) >= window_n and (time.time() - last_rezero) > rezero_cooldown_s:
                mags = []
                for r1, r2 in zip(imu1_window, imu2_window):
                    g1 = np.array([r1['Gx'], r1['Gy'], r1['Gz']], dtype=float) - joint_system.g1_bias
                    g2 = np.array([r2['Gx'], r2['Gy'], r2['Gz']], dtype=float) - joint_system.g2_bias
                    mags.append(np.linalg.norm(g1) + np.linalg.norm(g2))
                g_mean = float(np.mean(mags))
                if g_mean < rezero_gyro_thresh:
                    try:
                        joint_system.reestimate_gyro_bias_from_window(imu1_window, imu2_window)
                        joint_system.set_zero_reference_from_window(imu1_window, imu2_window, gyro_thresh=rezero_gyro_thresh)
                        last_rezero = time.time()
                        try:
                            if joint_system.persist_path:
                                joint_system.save_calibration(joint_system.persist_path)
                        except Exception:
                            pass
                        print(f"[measurement] mid-run re-zero at t={time.time()-start_time:.1f}s")
                    except Exception as e:
                        print(f"[measurement] mid-run re-zero failed: {e}")
        time.sleep(0.001)

    # save raw jsonl
    ts = int(time.time())
    raw_path = os.path.join(DATA_DIR, f"raw_{ts}.jsonl")
    with open(raw_path, 'w') as f:
        for p in packets:
            f.write(json.dumps(p) + "\n")
    print(f"Saved raw packets to {raw_path} (N={len(packets)})")

    # compute angles
    angles = []
    for p in packets:
        angle_deg = None
        if joint_system is not None and getattr(joint_system, "j1", None) is not None:
            try:
                angle_deg = joint_system.calculate_angle(p['IMU1'], p['IMU2'])
            except Exception:
                try:
                    angle_deg = process_packet_accel_angle(p)
                except Exception:
                    angle_deg = None
        else:
            try:
                angle_deg = process_packet_accel_angle(p)
            except Exception:
                angle_deg = None
        angles.append(angle_deg)

    out_path = os.path.join(DATA_DIR, out_filename)
    with open(out_path, 'w') as f:
        f.write("time_s,angle_deg\n")
        for i, a in enumerate(angles):
            ts_rel = i / sampling_rate_est if sampling_rate_est and sampling_rate_est > 0 else i
            f.write(f"{ts_rel:.3f},{a if a is not None else ''}\n")
    print(f"Saved angles to {out_path} (N={len(angles)})")

    # summary
    try:
        metrics = compute_stream_metrics(packets, sampling_rate=sampling_rate_est)
    except Exception as e:
        print(f"Error computing metrics: {e}")
        metrics = {}
    print("Summary metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
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

def run(esp_ip):
    # Force fresh calibration at each trial: remove existing calibration file (optional)
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

    # create joint_system with safer defaults
    joint_system = IMUJointAngle(delta_t=0.1, alpha=0.92, adaptive_alpha=True,
                                output_smooth_alpha=0.12, persist_path=CALIB_PATH, debug=True)

    try:
        imu1_cal = imu2_cal = None

        # ALWAYS recalibrate
        ok, imu1_cal, imu2_cal = calibration_phase(ws, joint_system, num_samples=100, timeout_s=40)
        if not ok:
            print("Calibration incomplete; continuing with best-effort.")

        # Try automatic zeroing (longer window)
        zero_ok = zeroing_phase(ws, joint_system, window_s=3.5, timeout_s=20.0,
                                sampling_rate_est=10.0, gyro_thresh=0.6)
        if not zero_ok:
            # fallback: deterministic accel-median from calibration frames
            try:
                if imu1_cal and imu2_cal and len(imu1_cal) >= 20:
                    joint_system.force_zero_from_accel_window(imu1_cal[:60], imu2_cal[:60], use_median=True)
                    # re-bias
                    joint_system.reestimate_gyro_bias_from_window(imu1_cal[:60], imu2_cal[:60])
                    print("[zeroing] fallback: forced accel-median zero from calibration frames.")
            except Exception as e:
                print(f"[zeroing] fallback failed: {e}")

        # post-zero preview: capture a few frames and show mean/std to confirm near-zero
        preview_n = 20
        preview_angles = []
        print("[preview] sampling a short preview (hold still)...")
        for _ in range(preview_n):
            pkt = ws.read_packet()
            if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
                try:
                    preview_angles.append(joint_system.calculate_angle(pkt['IMU1'], pkt['IMU2']))
                except Exception:
                    pass
            else:
                time.sleep(0.02)
        valid = [a for a in preview_angles if a is not None]
        if len(valid) > 0:
            print(f"[post-zero preview] mean={np.mean(valid):.3f} deg, std={np.std(valid):.3f} deg, n={len(valid)}")
        else:
            print("[post-zero preview] no valid preview angles")

        # Ask user to start measurement
        try:
            if os.getenv("AUTO_START", "0") != "1":
                input("Press Enter to start measurement (will run 30s)...")
            else:
                print("AUTO_START=1 — starting measurement.")
        except Exception:
            pass

        # run measurement
        measurement_phase(ws, joint_system=joint_system, duration_s=30, sampling_rate_est=10.0)
    finally:
        ws.close()

if __name__ == "__main__":
    ESP_IP = os.getenv("ESP_IP")
    if not ESP_IP:
        print("Warning: ESP_IP not set in environment.")
    print(f"Using ESP_IP = {ESP_IP}")
    run(ESP_IP)
