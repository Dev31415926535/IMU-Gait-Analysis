# src/main.py
import time
import os
import json
from ws_reader import IMUWebSocketReader
from imu_joint_angle import IMUJointAngle
from processors import process_packet_accel_angle, compute_stream_metrics
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'recordings')
os.makedirs(DATA_DIR, exist_ok=True)

def calibration_phase(ws, joint_system, num_samples=80, timeout_s=20):
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
        print("Calibration failed: not enough valid packets")
        return False
    calib_data = joint_system.collect_calibration_data(imu1, imu2)
    print("Identifying joint axis...")
    joint_system.identify_joint_axis(calib_data)
    print("Identifying joint position...")
    joint_system.identify_joint_position(calib_data)
    return True

def measurement_phase(ws, joint_system=None, duration_s=30, sampling_rate_est=10.0, out_filename="joint_angles.csv"):
    print("\n=== Measurement Phase ===")
    packets = []
    start = time.time()
    last = time.time()
    while (time.time() - start) < duration_s:
        pkt = ws.read_packet()
        if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
            packets.append(pkt)
        # small sleep to avoid busy loop
        time.sleep(0.005)
    # Save raw JSON lines
    ts = int(time.time())
    raw_path = os.path.join(DATA_DIR, f"raw_{ts}.jsonl")
    with open(raw_path, 'w') as f:
        for p in packets:
            f.write(json.dumps(p) + "\n")
    print(f"Saved raw packets to {raw_path} (N={len(packets)})")

    # If joint_system has been calibrated, use it; if not, fallback to accel-angle
    angles = []
    for p in packets:
        if joint_system is not None and joint_system.j1 is not None:
            try:
                angle = joint_system.calculate_angle(p['IMU1'], p['IMU2'])
            except Exception:
                angle = process_packet_accel_angle(p)
        else:
            angle = process_packet_accel_angle(p)
        angles.append(angle)

    # Save angles to CSV
    out_path = os.path.join(DATA_DIR, out_filename)
    with open(out_path, 'w') as f:
        f.write("time_s,angle_deg\n")
        for i, a in enumerate(angles):
            f.write(f"{i/sampling_rate_est:.3f},{a if a is not None else ''}\n")
    print(f"Saved angles to {out_path}")

    # compute summary metrics
    metrics = compute_stream_metrics(packets, sampling_rate=sampling_rate_est)
    print("Summary metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    return metrics

def run(esp_ip, do_calibration=True):
    ws = IMUWebSocketReader(esp_ip)
    if not ws.connect():
        print("Cannot connect to ESP32. Exiting.")
        return

    # Adjust delta_t estimate if you want
    joint_system = IMUJointAngle(delta_t=0.1)

    try:
        if do_calibration:
            ok = calibration_phase(ws, joint_system, num_samples=80, timeout_s=25)
            if not ok:
                print("Calibration incomplete; proceeding with accel-based angle fallback.")
        input("Press Enter to start measurement (will run 30s)...")
        measurement_phase(ws, joint_system=joint_system, duration_s=30, sampling_rate_est=10.0)
    finally:
        ws.close()

if __name__ == "__main__":
    # Replace with your ESP IP or accept CLI args
    ESP_IP = os.getenv("ESP_IP")
    print(ESP_IP)
    run(ESP_IP, do_calibration=True)




# # src/main.py
# import time
# import os
# import json
# from ws_reader import IMUWebSocketReader
# from imu_joint_angle import IMUJointAngle
# from processors import process_packet_accel_angle, compute_stream_metrics, compute_advanced_metrics

# DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'recordings')
# os.makedirs(DATA_DIR, exist_ok=True)

# def calibration_phase(ws, joint_system, num_samples=80, timeout_s=20):
#     print("=== Calibration Phase ===")
#     imu1 = []
#     imu2 = []
#     start = time.time()
#     while len(imu1) < num_samples and (time.time() - start) < timeout_s:
#         pkt = ws.read_packet()
#         if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
#             imu1.append(pkt['IMU1'])
#             imu2.append(pkt['IMU2'])
#             if len(imu1) % 10 == 0:
#                 print(f"Collected {len(imu1)}/{num_samples}")
#         else:
#             time.sleep(0.01)
#     if len(imu1) < 10:
#         print("Calibration failed: not enough valid packets")
#         return False
#     calib_data = joint_system.collect_calibration_data(imu1, imu2)
#     print("Identifying joint axis...")
#     joint_system.identify_joint_axis(calib_data)
#     print("Identifying joint position...")
#     joint_system.identify_joint_position(calib_data)
#     return True

# def measurement_phase(ws, joint_system=None, duration_s=30, sampling_rate_est=10.0, out_filename="joint_angles.csv"):
#     """
#     Collects packets for duration_s seconds, returns (angles, packets)
#     """
#     print("\n=== Measurement Phase ===")
#     packets = []
#     angles = []
#     start = time.time()
#     last = time.time()

#     try:
#         while (time.time() - start) < duration_s:
#             pkt = ws.read_packet()
#             if pkt and 'IMU1' in pkt and 'IMU2' in pkt:
#                 packets.append(pkt)

#                 # also compute angle in real-time (optional)
#                 if joint_system is not None and joint_system.j1 is not None:
#                     try:
#                         angle = joint_system.calculate_angle(pkt['IMU1'], pkt['IMU2'])
#                     except Exception:
#                         angle = process_packet_accel_angle(pkt)
#                 else:
#                     angle = process_packet_accel_angle(pkt)
#                 angles.append(angle)

#             # small sleep to avoid busy loop
#             time.sleep(0.005)
#     except KeyboardInterrupt:
#         print("\n⚠ Measurement interrupted by user")

#     # Save raw JSON lines
#     ts = int(time.time())
#     raw_path = os.path.join(DATA_DIR, f"raw_{ts}.jsonl")
#     with open(raw_path, 'w') as f:
#         for p in packets:
#             f.write(json.dumps(p) + "\n")
#     print(f"Saved raw packets to {raw_path} (N={len(packets)})")

#     # Save angles to CSV
#     out_path = os.path.join(DATA_DIR, out_filename)
#     with open(out_path, 'w') as f:
#         f.write("time_s,angle_deg\n")
#         for i, a in enumerate(angles):
#             f.write(f"{i/sampling_rate_est:.3f},{a if a is not None else ''}\n")
#     print(f"Saved angles to {out_path} (N={len(angles)})")

#     return angles, packets

# def run(esp_ip, do_calibration=True, sampling_rate_est=10.0, measurement_duration_s=30, leg_length_m=0.95):
#     ws = IMUWebSocketReader(esp_ip)
#     if not ws.connect():
#         print("Cannot connect to ESP32. Exiting.")
#         return

#     # Initialize joint angle system
#     joint_system = IMUJointAngle(delta_t=1.0/sampling_rate_est)

#     try:
#         # Calibration phase
#         if do_calibration:
#             ok = calibration_phase(ws, joint_system, num_samples=80, timeout_s=25)
#             if not ok:
#                 print("Calibration incomplete; proceeding with accel-based angle fallback.")

#         input(f"\nPress Enter to start measurement (will run {measurement_duration_s}s)...")
#         angles, packets = measurement_phase(ws, joint_system=joint_system,
#                                            duration_s=measurement_duration_s,
#                                            sampling_rate_est=sampling_rate_est,
#                                            out_filename="joint_angles.csv")

#         # compute basic metrics
#         print("\n--- Basic computed metrics ---")
#         metrics = compute_stream_metrics(packets, sampling_rate=sampling_rate_est)
#         for k, v in metrics.items():
#             print(f"  {k}: {v}")

#         # compute advanced metrics (stride lengths, speeds, HS/TO, summary)
#         print("\n--- Advanced computed metrics ---")
#         try:
#             adv = compute_advanced_metrics(packets, sampling_rate=sampling_rate_est, leg_length_m=leg_length_m)
#             # Nicely print adv, limit large arrays
#             for k, v in adv.items():
#                 if isinstance(v, (list, tuple)) and len(v) > 10:
#                     print(f"  {k}: array(len={len(v)})")
#                 else:
#                     print(f"  {k}: {v}")
#         except Exception as e:
#             print(f"Error computing advanced metrics: {e}")
#             import traceback
#             traceback.print_exc()

#     finally:
#         ws.close()
#         print("\nConnection closed. Program finished.")

# if __name__ == "__main__":
#     # Replace with your ESP IP or accept CLI args
#     ESP_IP = "10.62.139.36"   # update if needed
#     # sampling rate used to convert indices -> timestamps; set to your ESP effective rate
#     SAMPLING_RATE_EST = 10.0
#     MEASUREMENT_DURATION_S = 30
#     LEG_LENGTH_M = 0.95

#     run(ESP_IP, do_calibration=True, sampling_rate_est=SAMPLING_RATE_EST,
#         measurement_duration_s=MEASUREMENT_DURATION_S, leg_length_m=LEG_LENGTH_M)